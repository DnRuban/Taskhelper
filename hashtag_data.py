import re
import time
import typing
from typing import List
import datetime

import telebot
from telebot.types import MessageEntity

import config_utils
import db_utils
import hashtag_utils
import post_link_utils
import utils
from utils import SCHEDULED_DATETIME_FORMAT
from config_utils import DEFAULT_USER_DATA, HASHTAGS

PRIORITY_TAG = HASHTAGS["PRIORITY"]
OPENED_TAG = HASHTAGS["OPENED"]
CLOSED_TAG = HASHTAGS["CLOSED"]
SCHEDULED_TAG = HASHTAGS["SCHEDULED"]

POSSIBLE_PRIORITIES = ["1", "2", "3"]
SCHEDULED_DATE_FORMAT_REGEX = "^\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}"


class HashtagData:
	def __init__(self, post_data: telebot.types.Message, main_channel_id: int, insert_default_tags: bool = False):
		self.hashtag_indexes = []
		self.post_data = post_data
		self.main_channel_id = main_channel_id

		text, entities = utils.get_post_content(post_data)
		entities = self.remove_strikethrough_entities(text, entities)
		utils.set_post_content(post_data, text, entities)

		hashtags = self.extract_hashtags(post_data, main_channel_id)
		scheduled_tag, status_tag, user_tags, priority_tag = hashtags
		self.scheduled_tag = scheduled_tag
		self.status_tag = status_tag
		self.user_tags = user_tags
		self.priority_tag = priority_tag
		self.is_sent = None

		self.other_hashtags = self.extract_other_hashtags(post_data)

		missing_tags = self.get_assigned_user() is None or self.get_priority_number() is None or self.is_status_missing()
		if insert_default_tags and missing_tags:
			self.insert_default_tags()

		self.mentioned_users = self.find_mentioned_users(post_data)
		for user_tag in self.mentioned_users:
			if user_tag not in self.user_tags:
				self.user_tags.append(user_tag)

	def is_status_missing(self):
		return self.status_tag is None

	def is_opened(self):
		return self.status_tag == OPENED_TAG

	def is_closed(self):
		return self.status_tag == CLOSED_TAG

	def is_scheduled(self):
		return bool(self.scheduled_tag)

	def get_priority_number(self):
		if self.priority_tag and self.priority_tag != PRIORITY_TAG:
			return self.priority_tag[len(PRIORITY_TAG):]

	def get_priority_number_or_default(self):
		if self.priority_tag:
			if self.priority_tag == PRIORITY_TAG:
				return self.get_default_subchannel_priority()
			return self.priority_tag[len(PRIORITY_TAG):]

	def get_assigned_user(self):
		if self.user_tags:
			return self.user_tags[0]

	def get_followed_users(self):
		return self.user_tags[1:]

	def get_all_users(self):
		assigned_user = self.get_assigned_user()
		if not assigned_user:
			return
		user_tags = [assigned_user]
		user_tags += self.get_followed_users()
		return user_tags

	def get_hashtag_list(self):
		hashtags = [self.scheduled_tag, self.status_tag]
		hashtags += self.user_tags
		hashtags.append(self.priority_tag)
		return hashtags

	def get_hashtags_for_insertion(self):
		hashtags = []
		hashtags.append(self.status_tag)
		hashtags += self.user_tags
		hashtags.append(self.priority_tag)
		hashtags.append(self.scheduled_tag)
		return hashtags

	def set_status_tag(self, state: typing.Union[bool, None]):
		if state is None:
			self.status_tag = None
		else:
			self.status_tag = OPENED_TAG if state else CLOSED_TAG

	def assign_to_user(self, user: str):
		if user in self.user_tags:
			self.user_tags.remove(user)
		self.user_tags.insert(0, user)

	def set_priority(self, priority: str):
		self.priority_tag = PRIORITY_TAG + priority

	def remove_from_followers(self, user: str):
		self.user_tags.remove(user)

	def add_to_followers(self, user: str):
		if user not in self.user_tags:
			self.user_tags.append(user)

	def set_scheduled_tag(self, date):
		if date:
			self.scheduled_tag = SCHEDULED_TAG + " " + date
		else:
			self.scheduled_tag = None

	def get_scheduled_datetime_str(self):
		if not self.is_scheduled():
			return
		space_index = self.scheduled_tag.find(" ")
		return self.scheduled_tag[space_index + 1:]

	def set_scheduled_status(self, is_sent):
		self.is_sent = is_sent

	def insert_default_user(self, default_user):
		if not self.get_assigned_user():
			self.assign_to_user(default_user)

	def insert_default_priority(self):
		if self.get_priority_number() is None:
			if not self.find_priorities_in_other_hashtags():
				self.set_priority("")

	def insert_default_tags(self):
		main_channel_id_str = str(self.main_channel_id)
		if main_channel_id_str in DEFAULT_USER_DATA:
			self.status_tag = OPENED_TAG if self.is_status_missing() else self.status_tag
			user, priority = DEFAULT_USER_DATA[main_channel_id_str].split(" ")
			self.insert_default_user(user)
			self.insert_default_priority()

	def get_entities_to_ignore(self, text: str, entities: List[telebot.types.MessageEntity]):
		front_index = 0
		current_offset = 0
		while front_index < (len(entities)):
			next_entity = entities[front_index]

			if next_entity.type == "hashtag":
				self.update_scheduled_tag(text, entities, front_index)

			text_in_between = text[current_offset:next_entity.offset]
			spaces_only = all([i == ' ' for i in text_in_between])

			if not spaces_only:
				break

			if next_entity.type == "text_link":
				if post_link_utils.is_ticket_number_entity(self.post_data, text, next_entity):
					current_offset += next_entity.length + len(post_link_utils.LINK_ENDING)
					front_index += 1
					continue

			current_offset = next_entity.offset + next_entity.length
			front_index += 1

		last_new_line = text.rfind("\n")
		last_new_line = last_new_line if last_new_line >= 0 else len(text)
		back_index = len(entities) - 1
		current_offset = 0
		while back_index >= 0:
			previous_entity = entities[back_index]
			if previous_entity.offset < last_new_line:
				break

			if previous_entity.type == "hashtag":
				self.update_scheduled_tag(text, entities, back_index)

			text_in_between = text[previous_entity.offset + previous_entity.length:len(text)-current_offset]
			spaces_only = all([i == ' ' for i in text_in_between])
			if not spaces_only:
				break
			current_offset = len(text) - previous_entity.offset
			back_index -= 1

		if back_index < (front_index - 2):
			back_index = front_index
		return range(front_index, back_index + 1)

	def find_hashtag_indexes(self, text: str, entities: List[telebot.types.MessageEntity], main_channel_id: int):
		scheduled_tag_index = None
		status_tag_index = None
		user_tag_indexes = []
		priority_tag_index = None

		if entities is None:
			return None, None, [], None

		entities_to_ignore = self.get_entities_to_ignore(text, entities)

		for entity_index in reversed(range(len(entities))):
			if entity_index in entities_to_ignore:
				continue
			entity = entities[entity_index]
			if entity.type == "hashtag":
				tag = text[entity.offset + 1:entity.offset + entity.length]
				if config_utils.HASHTAGS_BEFORE_UPDATE and self.check_old_scheduled_tag(tag):
					scheduled_tag_index = entity_index
					continue

				if self.check_scheduled_tag(tag, SCHEDULED_TAG):
					scheduled_tag_index = entity_index
					continue

				if config_utils.HASHTAGS_BEFORE_UPDATE and self.check_old_status_tag(tag):
					status_tag_index = entity_index
					continue

				if tag == OPENED_TAG or tag == CLOSED_TAG:
					status_tag_index = entity_index
					continue

				if db_utils.is_user_tag_exists(main_channel_id, tag):
					user_tag_indexes.insert(0, entity_index)
					continue

				if config_utils.HASHTAGS_BEFORE_UPDATE and self.check_old_priority_tag(tag):
					priority_tag_index = entity_index
					continue

				if self.check_priority_tag(tag, PRIORITY_TAG):
					priority_tag_index = entity_index

		return scheduled_tag_index, status_tag_index, user_tag_indexes, priority_tag_index

	def extract_hashtags(self, post_data: telebot.types.Message, main_channel_id: int):
		text, entities = utils.get_post_content(post_data)

		self.hashtag_indexes = self.find_hashtag_indexes(text, entities, main_channel_id)
		scheduled_tag_index, status_tag_index, user_tag_indexes, priority_tag_index = self.hashtag_indexes

		scheduled_tag = None
		if scheduled_tag_index is not None:
			if config_utils.HASHTAGS_BEFORE_UPDATE:
				result = self.replace_old_scheduled_tag(text, entities, scheduled_tag_index)
				text = result if result else text
			self.update_scheduled_tag(text, entities, scheduled_tag_index)
			scheduled_tag = self.get_tag_from_entity(entities[scheduled_tag_index], text)

		status_tag = None
		if status_tag_index is not None:
			if config_utils.HASHTAGS_BEFORE_UPDATE:
				result = self.replace_old_status_tag(text, entities, status_tag_index)
				text = result if result else text
			status_tag = self.get_tag_from_entity(entities[status_tag_index], text)

		user_tags = []
		if user_tag_indexes:
			for user_tag_index in user_tag_indexes:
				user_tag = self.get_tag_from_entity(entities[user_tag_index], text)
				user_tags.append(user_tag)

		priority_tag = None
		if priority_tag_index is not None:
			if config_utils.HASHTAGS_BEFORE_UPDATE:
				result = self.replace_old_priority_tag(text, entities, priority_tag_index)
				text = result if result else text
			priority_tag = self.get_tag_from_entity(entities[priority_tag_index], text)

		return scheduled_tag, status_tag, user_tags, priority_tag

	def extract_other_hashtags(self, post_data: telebot.types.Message):
		text, entities = utils.get_post_content(post_data)
		if not entities:
			return []
		hashtags = []
		scheduled_tag_index, status_tag_index, user_tag_indexes, priority_tag_index = self.hashtag_indexes
		ignored_indexes = [scheduled_tag_index, status_tag_index, priority_tag_index]
		ignored_indexes += user_tag_indexes

		for entity_index in range(len(entities)):
			if entity_index in ignored_indexes or entities[entity_index].type != "hashtag":
				continue

			entity_text = self.get_tag_from_entity(entities[entity_index], text)
			hashtags.append("#" + entity_text)
		return hashtags
	
	def get_present_hashtag_indices(self):
		scheduled_tag_index, status_tag_index, user_tag_indexes, priority_tag_index = self.hashtag_indexes

		hashtags = [scheduled_tag_index, status_tag_index, priority_tag_index]
		if user_tag_indexes:
			hashtags += user_tag_indexes
		return list(filter(lambda elem: elem is not None, hashtags))

	def get_post_data_without_hashtags(self):
		text, entities = utils.get_post_content(self.post_data)

		entities_to_remove = self.get_present_hashtag_indices()
		entities_to_remove.sort(reverse=True)

		if not len(entities_to_remove):
			return self.post_data

		for entity_index in entities_to_remove:
			text, entities = utils.cut_entity_from_post(text, entities, entity_index)

		utils.set_post_content(self.post_data, text, entities)
		return self.post_data

	def get_default_subchannel_priority(self):
		main_channel_id_str = str(self.main_channel_id)
		if main_channel_id_str in DEFAULT_USER_DATA:
			user, priority = DEFAULT_USER_DATA[main_channel_id_str].split()
			return priority

	def find_mentioned_users(self, post_data: telebot.types.Message):
		text, entities = utils.get_post_content(post_data)
		mentioned_users = []
		scheduled_tag_index, status_tag_index, user_tag_indexes, priority_tag_index = self.hashtag_indexes
		ignored_indexes = [scheduled_tag_index, status_tag_index, priority_tag_index]
		ignored_indexes += user_tag_indexes

		for entity_index in range(len(entities)):
			if entity_index in ignored_indexes or entities[entity_index].type != "hashtag":
				continue

			tag = self.get_tag_from_entity(entities[entity_index], text)
			if db_utils.is_user_tag_exists(self.main_channel_id, tag):
				mentioned_users.append(tag)
		return mentioned_users

	def is_tag_in_other_hashtags(self, tag: str):
		if not tag.startswith("#"):
			tag = f"#{tag}"
		return tag in self.other_hashtags

	def find_priorities_in_other_hashtags(self):
		other_hashtags = [h[1:] for h in self.other_hashtags]
		priority_filter = lambda t: (t.startswith(PRIORITY_TAG)) and (t[len(PRIORITY_TAG):] in POSSIBLE_PRIORITIES)
		priority_tags = filter(priority_filter, other_hashtags)
		priorities = [int(p[len(PRIORITY_TAG):]) for p in priority_tags]
		return priorities

	def copy_tags_from_other_tags(self):
		if self.is_scheduled():
			pass
		elif self.status_tag is None:
			if self.is_tag_in_other_hashtags(OPENED_TAG):
				self.status_tag = OPENED_TAG
			elif self.is_tag_in_other_hashtags(CLOSED_TAG):
				self.status_tag = CLOSED_TAG
		elif self.status_tag != OPENED_TAG and self.is_tag_in_other_hashtags(OPENED_TAG):
			self.status_tag = OPENED_TAG

		priorities = self.find_priorities_in_other_hashtags()
		if priorities:
			current_priority = self.get_priority_number_or_default()
			highest_priority_from_other_tags = min(priorities)

			if current_priority is not None:
				current_priority = int(current_priority)
				if current_priority < highest_priority_from_other_tags:
					return
				priorities.append(current_priority)

			highest_priority = min(priorities)
			self.priority_tag = f"{PRIORITY_TAG}{highest_priority}"

	def remove_redundant_priority_tags(self, text: str, entities: List[MessageEntity]):
		entity_tags = [self.get_tag_from_entity(e, text) for e in entities]
		entities_to_ignore = self.get_entities_to_ignore(text, entities)

		_, _, _, priority_tag_index = self.hashtag_indexes

		if priority_tag_index is None:
			return text, entities
		highest_priority = [int(self.get_priority_number_or_default()), priority_tag_index]
		priority_entity_indexes = []
		for i in self.get_entity_deduplication_order(text, entities):
			entity = entities[i]
			tag = entity_tags[i]
			if i in entities_to_ignore or entity.type != "hashtag":
				continue

			if not tag.startswith(PRIORITY_TAG):
				continue

			priority = tag[len(PRIORITY_TAG):]
			if priority in POSSIBLE_PRIORITIES or priority == "":
				priority_entity_indexes.append(i)
				highest_priority_number, highest_priority_index = highest_priority
				if priority and int(priority) <= highest_priority_number:
					highest_priority = [int(priority), i]

		priority_entity_indexes.sort(reverse=True)
		highest_priority_number, highest_priority_index = highest_priority
		for entity_index in priority_entity_indexes:
			if entity_index == highest_priority_index:
				continue
			text, entities = utils.cut_entity_from_post(text, entities, entity_index)

		return text, entities

	def remove_redundant_status_tags(self, text: str, entities: List[MessageEntity]):
		entities_to_ignore = self.get_entities_to_ignore(text, entities)

		opened_tag_exists = False
		status_tag_indexes = []
		for i in self.get_entity_deduplication_order(text, entities):
			entity = entities[i]
			tag = self.get_tag_from_entity(entity, text)
			if i in entities_to_ignore or entity.type != "hashtag":
				continue

			if tag == OPENED_TAG:
				opened_tag_exists = True
				status_tag_indexes.append(i)
			elif tag == CLOSED_TAG:
				status_tag_indexes.append(i)

		if len(status_tag_indexes) < 1:
			return text, entities

		first_status_tag_index = status_tag_indexes[0]
		first_status_tag_entity = entities[first_status_tag_index]
		previous_status_offset = first_status_tag_entity.offset

		status_tag_str = "#" + (OPENED_TAG if opened_tag_exists else CLOSED_TAG)
		self.set_status_tag(opened_tag_exists)

		text, entities = hashtag_utils.insert_hashtag_in_post(text, entities, status_tag_str, previous_status_offset)
		for i, status_index in enumerate(status_tag_indexes):
			if status_index >= first_status_tag_index:
				status_tag_indexes[i] += 1

		status_tag_indexes.sort(reverse=True)
		for entity_index in status_tag_indexes:
			text, entities = utils.cut_entity_from_post(text, entities, entity_index)

		return text, entities

	def remove_redundant_scheduled_tags(self, text: str, entities: List[MessageEntity]):
		entities_to_ignore = self.get_entities_to_ignore(text, entities)

		scheduled_tag_indexes = []
		remained_text = []
		earliest_datetime_str = None
		earliest_tag_time = None
		for i in self.get_entity_deduplication_order(text, entities):
			entity = entities[i]
			tag = self.get_tag_from_entity(entity, text)
			is_scheduled_tag = tag == SCHEDULED_TAG or tag.startswith(SCHEDULED_TAG + " ")
			if i in entities_to_ignore or entity.type != "hashtag" or not is_scheduled_tag:
				continue

			scheduled_tag_indexes.append(i)

			scheduled_parts = tag.split(" ")
			if len(scheduled_parts) < 2:
				continue

			date_str = scheduled_parts[1]
			if not utils.check_datetime(date_str, "%Y-%m-%d"):
				remained_text.append(date_str)
				if len(scheduled_parts) > 2:
					remained_text.append(scheduled_parts[2])
				continue

			if len(scheduled_parts) < 3:
				time_str = "00:00"
			else:
				time_str = scheduled_parts[2]
				if not utils.check_datetime(time_str, "%H:%M"):
					remained_text.append(time_str)
					time_str = "00:00"

			datetime_str = f"{date_str} {time_str}"
			scheduled_date = datetime.datetime.strptime(datetime_str, SCHEDULED_DATETIME_FORMAT)
			current_timestamp = scheduled_date.timestamp()
			if not earliest_tag_time:
				earliest_tag_time = current_timestamp
				earliest_datetime_str = datetime_str
			elif earliest_tag_time > current_timestamp:
				earliest_tag_time = current_timestamp
				earliest_datetime_str = datetime_str

		if len(scheduled_tag_indexes) < 1:
			return text, entities

		if len(remained_text) > 0:
			last_main_entity = entities[entities_to_ignore.start - 1]
			insertion_start = last_main_entity.offset + last_main_entity.length
			changed_offset = 0
			for s in remained_text[::-1]:
				str_to_insert = f" {s}"
				text = text[:insertion_start] + str_to_insert + text[insertion_start:]
				changed_offset += len(str_to_insert)
			utils.offset_entities(entities[entities_to_ignore.start:], changed_offset)

		scheduled_tag_indexes.sort(reverse=True)
		insertion_offset = entities[scheduled_tag_indexes[-1]].offset
		for entity_index in scheduled_tag_indexes:
			text, entities = utils.cut_entity_from_post(text, entities, entity_index)

		if earliest_datetime_str:
			scheduled_tag_str = f"#{SCHEDULED_TAG} {earliest_datetime_str}"
			text, entities = hashtag_utils.insert_hashtag_in_post(text, entities, scheduled_tag_str, insertion_offset)
		else:
			self.set_scheduled_tag(None)

		return text, entities

	def remove_duplicates(self, post_data: telebot.types.Message):
		text, entities = utils.get_post_content(post_data)
		entity_tags = [self.get_tag_from_entity(e, text) for e in entities]
		entities_to_ignore = self.get_entities_to_ignore(text, entities)

		checked_tags = []

		entities_to_remove = []
		for i in self.get_entity_deduplication_order(text, entities):
			entity = entities[i]
			tag = entity_tags[i]
			if i in entities_to_ignore or entity.type != "hashtag":
				continue

			if tag not in checked_tags:
				checked_tags.append(tag)
			else:
				entities_to_remove.append(i)

		entities_to_remove.sort(reverse=True)
		for entity_index in entities_to_remove:
			text, entities = utils.cut_entity_from_post(text, entities, entity_index)
		self.hashtag_indexes = self.find_hashtag_indexes(text, entities, self.main_channel_id)

		text, entities = self.remove_redundant_priority_tags(text, entities)
		text, entities = self.remove_redundant_scheduled_tags(text, entities)
		text, entities = self.remove_redundant_status_tags(text, entities)

		utils.set_post_content(post_data, text, entities)
		return post_data

	def rearrange_hashtags(self, post_data: telebot.types.Message):
		self.copy_tags_from_other_tags()
		hashtags = self.get_hashtags_for_insertion()
		hashtag_utils.insert_hashtags(post_data, hashtags)

		post_data = self.remove_duplicates(post_data)
		self.extract_hashtags(post_data, self.main_channel_id)
		post_data = self.add_strikethrough_entities(post_data)

		return post_data

	def add_strikethrough_entities(self, post_data):
		text, entities = utils.get_post_content(post_data)

		if self.is_sent:
			entities = self.strike_through_scheduled_tag(text, entities)
		if self.is_closed():
			entities = self.strike_through_ticket_number(text, entities)

		utils.set_post_content(post_data, text, entities)
		return post_data

	def remove_strikethrough_entities(self, text, entities):
		entities_to_ignore = self.get_entities_to_ignore(text, entities)
		entities_to_remove = []
		for i, entity in enumerate(entities):
			if i in entities_to_ignore:
				continue

			if entity.type != "strikethrough":
				continue

			if post_link_utils.is_ticket_number_entity(self.post_data, text, entity):
				entities_to_remove.append(entity)
				continue

			if i == 0:
				continue

			previous_entity = entities[i - 1]
			if previous_entity.type != "hashtag":
				continue

			previous_entity_str = "#" + self.get_tag_from_entity(previous_entity, text)
			scheduled_tag_start = f"#{SCHEDULED_TAG} "
			if not previous_entity_str.startswith(scheduled_tag_start):
				continue

			if not entity.offset == (previous_entity.offset + len(scheduled_tag_start)):
				continue
			if not entity.length == (previous_entity.length - len(scheduled_tag_start)):
				continue

			entities_to_remove.append(entity)

		return [e for e in entities if e not in entities_to_remove]

	def strike_through_scheduled_tag(self, text, entities):
		scheduled_tag_index, _, _, _ = self.hashtag_indexes
		if not scheduled_tag_index:
			return text, entities
		scheduled_tag_entity = entities[scheduled_tag_index]
		scheduled_tag = self.get_tag_from_entity(scheduled_tag_entity, text)
		datetime_offset = scheduled_tag.find(" ") + 1
		datetime_str = scheduled_tag[datetime_offset:]

		strikethrough_offset = scheduled_tag_entity.offset + 1 + datetime_offset  # +1 because of the hashtag

		strikethrough_entity = MessageEntity(type="strikethrough", offset=strikethrough_offset, length=len(datetime_str))
		entities.append(strikethrough_entity)
		entities.sort(key=lambda e: e.offset)

		return entities

	def strike_through_ticket_number(self, text, entities):
		ticket_number_entity = None
		for entity in entities:
			if post_link_utils.is_ticket_number_entity(self.post_data, text, entity):
				ticket_number_entity = entity
				break

		if not ticket_number_entity:
			return entities

		strikethrough_entity = MessageEntity(
			type="strikethrough",
			offset=ticket_number_entity.offset,
			length=ticket_number_entity.length,
		)
		entities.insert(0, strikethrough_entity)

		return entities

	@staticmethod
	def get_entity_deduplication_order(text: str, entities: List[telebot.types.MessageEntity]):
		if not hashtag_utils.is_last_line_contains_only_hashtags(text, entities):
			return range(len(entities))

		last_line_start = text.rfind("\n")
		last_line_entities = []
		other_entities = []
		for i, entity in enumerate(entities):
			if entity.offset > last_line_start:
				last_line_entities.append(i)
			else:
				other_entities.append(i)

		return last_line_entities + other_entities

	@staticmethod
	def update_scheduled_tag(text: str, entities: List[telebot.types.MessageEntity], tag_index: int):
		scheduled_tag = entities[tag_index]
		if text[scheduled_tag.offset + 1:].startswith(SCHEDULED_TAG):
			text_after_tag = text[scheduled_tag.offset + scheduled_tag.length + 1:]
			result = re.search(SCHEDULED_DATE_FORMAT_REGEX, text_after_tag)
			if result is None:
				return False
			entities[tag_index].length += 1 + result.end()
			return True
		return False

	@staticmethod
	def get_tag_from_entity(entity: telebot.types.MessageEntity, text: str):
		return text[entity.offset + 1:entity.offset + entity.length]

	@staticmethod
	def check_priority_tag(tag, priority_tag):
		if not tag.startswith(priority_tag):
			return False
		return tag == priority_tag or tag[len(priority_tag):] in POSSIBLE_PRIORITIES

	@staticmethod
	def check_scheduled_tag(tag, scheduled_tag):
		if tag == scheduled_tag or tag.startswith(scheduled_tag + " "):
			return True
		return False

	@staticmethod
	def check_old_status_tag(tag: str):
		old_opened_tag = config_utils.HASHTAGS_BEFORE_UPDATE["OPENED"]
		old_closed_tag = config_utils.HASHTAGS_BEFORE_UPDATE["CLOSED"]
		if tag == old_opened_tag or tag == old_closed_tag:
			return True
		return False

	@staticmethod
	def check_old_scheduled_tag(tag: str):
		old_scheduled_tag = config_utils.HASHTAGS_BEFORE_UPDATE["SCHEDULED"]
		if HashtagData.check_scheduled_tag(tag, old_scheduled_tag):
			return True
		return False

	@staticmethod
	def check_old_priority_tag(tag: str):
		if HashtagData.check_priority_tag(tag, config_utils.HASHTAGS_BEFORE_UPDATE["PRIORITY"]):
			return True
		return False

	@staticmethod
	def replace_old_status_tag(text: str, entities: List[telebot.types.MessageEntity], entity_index: int):
		tag = text[entities[entity_index].offset + 1:entities[entity_index].offset + entities[entity_index].length]
		old_opened_tag = config_utils.HASHTAGS_BEFORE_UPDATE["OPENED"]
		old_closed_tag = config_utils.HASHTAGS_BEFORE_UPDATE["CLOSED"]
		if tag == old_opened_tag or tag == old_closed_tag:
			position = entities[entity_index].offset
			text, entities = utils.cut_entity_from_post(text, entities, entity_index)
			if tag == old_opened_tag:
				new_hashtag = OPENED_TAG
			else:
				new_hashtag = CLOSED_TAG
			text, entities = hashtag_utils.insert_hashtag_in_post(text, entities, "#" + new_hashtag, position)
			return text

	@staticmethod
	def replace_old_scheduled_tag(text: str, entities: List[telebot.types.MessageEntity], entity_index: int):
		tag = text[entities[entity_index].offset + 1:entities[entity_index].offset + entities[entity_index].length]
		old_scheduled_tag = config_utils.HASHTAGS_BEFORE_UPDATE["SCHEDULED"]
		if tag.startswith(old_scheduled_tag):
			scheduled_date = tag[len(old_scheduled_tag):]
			position = entities[entity_index].offset
			text, entities = utils.cut_entity_from_post(text, entities, entity_index)
			updated_tag_text = "#" + SCHEDULED_TAG + scheduled_date
			text, entities = hashtag_utils.insert_hashtag_in_post(text, entities, updated_tag_text, position)
			return text

	@staticmethod
	def replace_old_priority_tag(text: str, entities: List[telebot.types.MessageEntity], entity_index: int):
		tag = text[entities[entity_index].offset + 1:entities[entity_index].offset + entities[entity_index].length]
		old_priority_tag = config_utils.HASHTAGS_BEFORE_UPDATE["PRIORITY"]
		if tag.startswith(old_priority_tag):
			position = entities[entity_index].offset
			text, entities = utils.cut_entity_from_post(text, entities, entity_index)
			new_hashtag = PRIORITY_TAG + tag[len(old_priority_tag):]
			text, entities = hashtag_utils.insert_hashtag_in_post(text, entities, "#" + new_hashtag, position)
			return text
