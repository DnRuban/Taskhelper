import logging
from typing import List
import time
import datetime

import telebot.types
from telebot.apihelper import ApiTelegramException

import config_utils
import db_utils
import threading_utils
import channel_manager
from config_utils import MAX_BUTTONS_IN_ROW

SAME_MSG_CONTENT_ERROR = "Bad Request: message is not modified: specified new message content and reply markup are exactly the same as a current content and reply markup of the message"
MSG_CANT_BE_DELETED_ERROR = "message can't be deleted"
MSG_NOT_FOUND_ERROR = "message to delete not found"
KICKED_FROM_CHANNEL_ERROR = "Forbidden: bot was kicked from the channel chat"
SCHEDULED_DATETIME_FORMAT = "%Y-%m-%d %H:%M"


def create_callback_str(callback_prefix, callback_type, *args):
	arguments_str = ",".join([str(arg) for arg in args])
	components = [callback_prefix, callback_type]
	if arguments_str:
		components.append(arguments_str)
	callback_str = ",".join(components)
	return callback_str


def parse_callback_str(callback_str: str):
	components = callback_str.split(",")
	callback_type = components[1]
	arguments = components[2:]
	return callback_type, arguments


def offset_entities(entities, offset):
	if not entities:
		return []

	for entity in entities:
		entity.offset += offset

	return entities


def get_forwarded_from_id(message_data):
	if message_data.forward_from_chat:
		return message_data.forward_from_chat.id
	if message_data.forward_from:
		return message_data.forward_from.id

	return None


def get_post_content(post_data: telebot.types.Message):
	if post_data.text is not None:
		return post_data.text, post_data.entities
	elif post_data.caption is not None:
		return post_data.caption, post_data.caption_entities

	return "", []


def set_post_content(post_data: telebot.types.Message, text: str, entities: telebot.types.MessageEntity):
	if post_data.text is not None:
		post_data.text = text
		post_data.entities = entities
	else:
		post_data.caption = text
		post_data.caption_entities = entities


@threading_utils.timeout_error_lock
def edit_message_content(bot: telebot.TeleBot, post_data: telebot.types.Message, **kwargs):
	if "chat_id" not in kwargs:
		kwargs["chat_id"] = post_data.chat.id
	if "message_id" not in kwargs:
		kwargs["message_id"] = post_data.message_id
	if "text" not in kwargs:
		kwargs["text"] = post_data.text if post_data.text else post_data.caption
	if "entities" not in kwargs:
		kwargs["entities"] = post_data.entities if post_data.entities else post_data.caption_entities

	try:
		if post_data.text is not None:
			bot.edit_message_text(**kwargs)
		else:
			kwargs["caption"] = kwargs.pop("text")
			kwargs["caption_entities"] = kwargs.pop("entities")
			bot.edit_message_caption(**kwargs)
	except ApiTelegramException as E:
		if E.error_code == 429:
			raise E
		if E.description == SAME_MSG_CONTENT_ERROR:
			return


def is_post_data_equal(post_data1: telebot.types.Message, post_data2: telebot.types.Message):
	text1, entities1 = get_post_content(post_data1)
	text2, entities2 = get_post_content(post_data2)

	if text1 != text2:
		return False

	if entities1 is None and entities2 is None:
		return True

	if len(entities1) != len(entities2):
		return False

	for entity_i in range(len(entities1)):
		e1 = entities1[entity_i]
		e2 = entities2[entity_i]
		if e1.type != e2.type or e1.offset != e2.offset or e1.url != e2.url:
			return False

		if e1.type == "hashtag":
			return True  # for hashtags length is ignored because length of scheduled tags can be changed
		else:
			return e1.length == e2.length

	return True


def place_buttons_in_rows(buttons: List[telebot.types.InlineKeyboardButton]):
	rows = [[]]
	current_row = button_counter = 0
	for button in buttons:
		if button_counter < MAX_BUTTONS_IN_ROW:
			rows[current_row].append(button)
			button_counter += 1
		else:
			button_counter = 1
			current_row += 1
			rows.append([button])

	return rows


@threading_utils.timeout_error_lock
def edit_message_keyboard(bot: telebot.TeleBot, post_data: telebot.types.Message,
                          keyboard: telebot.types.InlineKeyboardMarkup = None, chat_id: int = None, message_id: int = None):
	if chat_id is None and message_id is None:
		chat_id = post_data.chat.id
		message_id = post_data.message_id

	if keyboard is None:
		keyboard = post_data.reply_markup

	if db_utils.is_individual_channel_exists(chat_id):
		newest_message_id = db_utils.get_newest_copied_message(chat_id)
		if message_id == newest_message_id:
			settings_button = telebot.types.InlineKeyboardButton("Settings ⚙️")
			settings_button.callback_data = create_callback_str(
				channel_manager.CALLBACK_PREFIX,
				channel_manager.CB_TYPES.SEND_CHANNEL_SETTINGS
			)
			keyboard.keyboard.append([telebot.types.InlineKeyboardButton(" ", callback_data="_")])
			keyboard.keyboard.append([settings_button])

	try:
		bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
	except ApiTelegramException as E:
		if E.error_code == 429:
			raise E
		if E.description == SAME_MSG_CONTENT_ERROR:
			return
		logging.info(f"Exception during adding keyboard - {E}")


def cut_entity_from_post(text: str, entities: List[telebot.types.MessageEntity], entity_index: int):
	entity_to_cut = entities[entity_index]
	if len(text) > entity_to_cut.offset + entity_to_cut.length:
		character_after_entity = text[entity_to_cut.offset + entity_to_cut.length]
		if character_after_entity == " ":
			entity_to_cut.length += 1
	elif text[entity_to_cut.offset - 1] == " ":
		# remove space before last tag if it's at the end of the line
		entity_to_cut.offset -= 1
		entity_to_cut.length += 1

	end = text[entity_to_cut.offset + entity_to_cut.length:]
	text = text[:entity_to_cut.offset] + end
	offsetted_entities = offset_entities(entities[entity_index + 1:], -entity_to_cut.length)
	entities[entity_index:] = offsetted_entities

	return text, entities


def get_key_by_value(d: dict, value: object):
	key_list = list(d.keys())
	val_list = list(d.values())

	try:
		position = val_list.index(value)
	except ValueError:
		return

	return key_list[position]


@threading_utils.timeout_error_lock
def delete_message(bot: telebot.TeleBot, chat_id: int, message_id: int):
	try:
		return bot.delete_message(chat_id=chat_id, message_id=message_id)
	except ApiTelegramException as E:
		if E.description.endswith(MSG_NOT_FOUND_ERROR):
			return True
		else:
			raise E


def get_last_message(bot: telebot.TeleBot, channel_id: int):
	last_message_id = db_utils.get_last_message_id(channel_id)
	if last_message_id is None:
		msg_text = "(This is service message for obtaining last message id, bot will delete it in a moment)"
		try:
			last_message = bot.send_message(chat_id=channel_id, text=msg_text)
			bot.delete_message(chat_id=channel_id, message_id=last_message.message_id)
		except Exception as E:
			logging.error(f"Error during retrieving last message id in {channel_id} - {E}")
			return
		last_message_id = last_message.message_id - 1
		db_utils.insert_or_update_last_msg_id(last_message_id, channel_id)

	return last_message_id


def check_last_messages(bot: telebot.TeleBot):
	channels_to_check = set()

	main_channel_ids = db_utils.get_main_channel_ids()
	if main_channel_ids:
		channels_to_check.update(main_channel_ids)

	for main_channel_id in config_utils.DISCUSSION_CHAT_DATA:
		discussion_channel_id = config_utils.DISCUSSION_CHAT_DATA[main_channel_id]
		if discussion_channel_id:
			channels_to_check.add(discussion_channel_id)

	for channel_id in channels_to_check:
		get_last_message(bot, channel_id)


@threading_utils.timeout_error_lock
def add_comment_to_ticket(bot: telebot.TeleBot, post_data: telebot.types.Message, text: str, entities: list = None):
	main_message_id = post_data.message_id
	main_channel_id = post_data.chat.id
	comment_message_id = db_utils.get_discussion_message_id(main_message_id, main_channel_id)
	if comment_message_id:
		main_channel_id_str = str(main_channel_id)
		discussion_chat_id = config_utils.DISCUSSION_CHAT_DATA[main_channel_id_str]
		if discussion_chat_id is None:
			return
		comment_msg = bot.send_message(chat_id=discussion_chat_id, reply_to_message_id=comment_message_id, text=text, entities=entities)
		db_utils.insert_comment_message(comment_message_id, comment_msg.id, discussion_chat_id, config_utils.BOT_ID)
		db_utils.set_ticket_update_time(main_message_id, main_channel_id, int(time.time()))


@threading_utils.timeout_error_lock
def get_message_content_by_id(bot: telebot.TeleBot, chat_id: int, message_id: int):
	try:
		forwarded_message = bot.forward_message(chat_id=config_utils.DUMP_CHAT_ID, from_chat_id=chat_id,
												message_id=message_id)
		bot.delete_message(chat_id=config_utils.DUMP_CHAT_ID, message_id=forwarded_message.message_id)
	except ApiTelegramException as E:
		if E.error_code == 429:
			raise E
		logging.error(f"Error during getting message {[message_id, chat_id]} content - {E}")
		return

	return forwarded_message


@threading_utils.timeout_error_lock
def copy_message(bot: telebot.TeleBot, **kwargs):
	return bot.copy_message(**kwargs)


@threading_utils.timeout_error_lock
def remove_keyboard(bot: telebot.TeleBot, chat_id: int, message_id: int):
	bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)


@threading_utils.timeout_error_lock
def get_main_message_content_by_id(bot: telebot.TeleBot, chat_id: int, message_id: int):
	try:
		forwarded_message = bot.forward_message(chat_id=config_utils.DUMP_CHAT_ID, from_chat_id=chat_id,
												message_id=message_id)
		bot.delete_message(chat_id=config_utils.DUMP_CHAT_ID, message_id=forwarded_message.message_id)
	except ApiTelegramException as E:
		if E.error_code == 429:
			raise E
		elif E.description == "Bad Request: message to forward not found":
			raise E
		elif E.description == "Bad Request: MESSAGE_ID_INVALID":
			# for some reason telegram throws this error if after deleting a message
			# no other actions were performed in this channel
			# instead of regular "message to forward not found" error
			raise E
		logging.error(f"Error during getting message content - {E}")
		return

	return forwarded_message


def check_content_type(bot: telebot.TeleBot, message: telebot.types.Message):
	if message.content_type not in config_utils.SUPPORTED_CONTENT_TYPES:
		if message.reply_markup:
			chat_id = message.chat.id
			message_id = message.message_id
			remove_keyboard(bot, chat_id, message_id)
		return False
	return True


def check_datetime(datetime_str, template_str):
	try:
		return datetime.datetime.strptime(datetime_str, template_str)
	except ValueError:
		return
