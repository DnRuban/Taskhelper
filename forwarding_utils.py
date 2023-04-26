import logging
import copy
from typing import List

import telebot
from telebot.apihelper import ApiTelegramException
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, MessageEntity

import db_utils
import hashtag_utils
import utils

from config_utils import SUBCHANNEL_DATA, DISCUSSION_CHAT_DATA, DEFAULT_USER_DATA, DUMP_CHAT_ID, \
	AUTO_FORWARDING_ENABLED

CALLBACK_PREFIX = "FWRD"

CHECK_MARK_CHARACTER = "\U00002705"
COMMENTS_CHARACTER = "\U0001F4AC"

OPENED_TICKED_CHARACTER = "\U0001F7E9"
CLOSED_TICKED_CHARACTER = "\U00002705"

BOT_ID = 0


class CB_TYPES:
	CHANGE_SUBCHANNEL = "SUB"
	CHANGE_PRIORITY = "PR"
	CLOSE = "X"
	OPEN = "O"
	SAVE = "S"
	SHOW_SUBCHANNELS = "R"
	SHOW_PRIORITIES = "P"
	SHOW_CC = "CC"
	TOGGLE_CC = "TCC"


def get_message_content_by_id(bot: telebot.TeleBot, chat_id: int, message_id: int):
	try:
		forwarded_message = bot.forward_message(chat_id=DUMP_CHAT_ID, from_chat_id=chat_id,
												message_id=message_id)
		bot.delete_message(chat_id=DUMP_CHAT_ID, message_id=forwarded_message.message_id)
	except ApiTelegramException as E:
		if E.error_code == 429:
			raise E
		return

	return forwarded_message


def forward_to_subchannel(bot: telebot.TeleBot, post_data: telebot.types.Message, hashtags: List[str]):
	main_channel_id = post_data.chat.id
	message_id = post_data.message_id

	forwarded_messages = db_utils.get_copied_message_data(message_id, main_channel_id)
	subchannels_to_ignore = []
	for forwarded_message in forwarded_messages:
		forwarded_msg_id, forwarded_channel_id = forwarded_message
		forwarded_msg_data = get_message_content_by_id(bot, forwarded_channel_id, forwarded_msg_id)
		if forwarded_msg_data and utils.is_post_data_equal(forwarded_msg_data, post_data):
			subchannels_to_ignore.append(forwarded_channel_id)  # ignore unchanged posts
			continue

		try:
			bot.delete_message(chat_id=forwarded_channel_id, message_id=forwarded_msg_id)
			db_utils.delete_copied_message(forwarded_msg_id, forwarded_channel_id)
		except ApiTelegramException as E:
			if E.error_code == 429:
				raise E
			elif E.description.endswith("message to delete not found"):
				db_utils.delete_copied_message(forwarded_msg_id, forwarded_channel_id)
			logging.info(f"Exception during delete_message [{forwarded_msg_id}, {forwarded_channel_id}] - {E}")

	if hashtag_utils.OPENED_TAG not in hashtags:
		return

	subchannel_ids = get_subchannel_ids_from_hashtags(main_channel_id, hashtags)
	if not subchannel_ids:
		logging.warning(f"Subchannel not found in config file {hashtags}, {main_channel_id}")
		return

	for subchannel_id in subchannel_ids:
		if subchannel_id in subchannels_to_ignore:
			continue

		try:
			copied_message = bot.copy_message(chat_id=subchannel_id, message_id=message_id, from_chat_id=main_channel_id)
			logging.info(f"Successfully forwarded post [{message_id}, {main_channel_id}] to {subchannel_id} subchannel by tags: {hashtags}")
		except ApiTelegramException as E:
			if E.error_code == 429:
				raise E
			logging.warning(f"Exception during forwarding post to subchannel {hashtags} - {E}")
			continue

		db_utils.insert_copied_message(message_id, main_channel_id, copied_message.message_id, subchannel_id)


def get_subchannel_ids_from_hashtags(main_channel_id: int, hashtags: List[str]):
	main_channel_id_str = str(main_channel_id)
	if main_channel_id_str not in SUBCHANNEL_DATA:
		return

	priority = None
	user_priority_list = None
	found_user = None

	subchannel_users = SUBCHANNEL_DATA[main_channel_id_str]

	user_tag = hashtags[1]
	if user_tag in subchannel_users:
		user_priority_list = subchannel_users[user_tag]
		found_user = user_tag

	if not user_priority_list:
		return

	for hashtag in hashtags:
		if hashtag and hashtag.startswith(hashtag_utils.PRIORITY_TAG):
			priority = hashtag[len(hashtag_utils.PRIORITY_TAG):]

	current_subchannel_id = None

	if priority == "" and main_channel_id_str in DEFAULT_USER_DATA:
		user, priority = DEFAULT_USER_DATA[main_channel_id_str].split()
		if user == found_user:
			current_subchannel_id = user_priority_list[priority]
	elif priority in user_priority_list:
		current_subchannel_id = user_priority_list[priority]
	else:
		return

	all_subchannel_ids = [current_subchannel_id]
	for followed_user in hashtags[2:-1]:
		if followed_user not in subchannel_users:
			continue

		user_subchannels = subchannel_users[followed_user]
		if priority not in user_subchannels:
			continue

		user_subchannel = user_subchannels[priority]
		all_subchannel_ids.append(user_subchannel)

	return all_subchannel_ids


def generate_control_buttons(hashtags: List[str], post_data: telebot.types.Message):
	main_channel_id = post_data.chat.id
	message_id = post_data.message_id

	if hashtags[0] == hashtag_utils.OPENED_TAG:
		state_switch_callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.CLOSE)
		state_switch_button = InlineKeyboardButton(OPENED_TICKED_CHARACTER, callback_data=state_switch_callback_data)
	else:
		state_switch_callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.OPEN)
		state_switch_button = InlineKeyboardButton(CLOSED_TICKED_CHARACTER, callback_data=state_switch_callback_data)

	reassign_callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SHOW_SUBCHANNELS)
	current_user = hashtags[1] if hashtags[1] is not None else "-"
	reassign_button = InlineKeyboardButton(f"➔ {current_user}", callback_data=reassign_callback_data)

	priority_callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SHOW_PRIORITIES)
	current_priority = "-"
	if hashtags[-1] is not None and hashtags[-1] != hashtag_utils.PRIORITY_TAG:
		current_priority = hashtags[-1]
		current_priority = current_priority[len(hashtag_utils.PRIORITY_TAG):]

	priority_button = InlineKeyboardButton(current_priority, callback_data=priority_callback_data)

	cc_callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SHOW_CC)
	cc_button = InlineKeyboardButton(f"CC", callback_data=cc_callback_data)

	buttons = [
		state_switch_button,
		reassign_button,
		cc_button,
		priority_button
	]

	main_channel_id_str = str(main_channel_id)
	if main_channel_id_str in DISCUSSION_CHAT_DATA and DISCUSSION_CHAT_DATA[main_channel_id_str] is not None:
		discussion_chat_id = DISCUSSION_CHAT_DATA[main_channel_id_str]
		discussion_message_id = db_utils.get_discussion_message_id(message_id, main_channel_id)
		if discussion_message_id:
			discussion_chat_id = str(discussion_chat_id)[4:]
			comments_url = f"tg://privatepost?channel={discussion_chat_id}&post={discussion_message_id}&thread={discussion_message_id}"
			comments_amount_text = f" ({db_utils.get_comments_count(message_id, main_channel_id, BOT_ID)})"
			comments_button = InlineKeyboardButton(COMMENTS_CHARACTER + comments_amount_text, url=comments_url)
			buttons.append(comments_button)

	keyboard_markup = InlineKeyboardMarkup([buttons])
	return keyboard_markup


def generate_subchannel_buttons(post_data: telebot.types.Message):
	main_channel_id = post_data.chat.id

	forwarding_data = get_subchannels_forwarding_data(main_channel_id)

	text, entities = utils.get_post_content(post_data)

	_, user_hashtag_indexes, priority_hashtag_index = hashtag_utils.find_hashtag_indexes(text, entities, main_channel_id)
	current_subchannel_name = ""

	if user_hashtag_indexes:
		user_hashtag_index = user_hashtag_indexes[0]
		entity = entities[user_hashtag_index]
		current_subchannel_name += text[entity.offset + 1:entity.offset + entity.length]
		if priority_hashtag_index is not None:
			entity = entities[priority_hashtag_index]
			priority = text[entity.offset + 1 + len(hashtag_utils.PRIORITY_TAG):entity.offset + entity.length]
			current_subchannel_name += " " + priority

	subchannel_buttons = []
	for subchannel_name in forwarding_data:
		callback_str = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.CHANGE_SUBCHANNEL, subchannel_name)
		btn = InlineKeyboardButton("#" + subchannel_name, callback_data=callback_str)
		if subchannel_name == current_subchannel_name:
			btn.text += CHECK_MARK_CHARACTER
			btn.callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SAVE)
		subchannel_buttons.append(btn)

	rows = utils.place_buttons_in_rows(subchannel_buttons)

	keyboard_markup = InlineKeyboardMarkup(rows)
	return keyboard_markup


def generate_priority_buttons(post_data: telebot.types.Message):
	main_channel_id = post_data.chat.id

	text, entities = utils.get_post_content(post_data)

	available_priorities = ["1", "2", "3"]

	_, user_hashtag_indexes, priority_hashtag_index = hashtag_utils.find_hashtag_indexes(text, entities, main_channel_id)
	current_user = ""
	current_priority = ""
	if user_hashtag_indexes:
		user_hashtag_index = user_hashtag_indexes[0]
		entity = entities[user_hashtag_index]
		current_user = text[entity.offset + 1:entity.offset + entity.length]
	if priority_hashtag_index is not None:
		entity = entities[priority_hashtag_index]
		current_priority = text[entity.offset + 1 + len(hashtag_utils.PRIORITY_TAG):entity.offset + entity.length]

	main_channel_id_str = str(main_channel_id)
	if main_channel_id_str in SUBCHANNEL_DATA:
		users = SUBCHANNEL_DATA[main_channel_id_str]
		if current_user in users:
			available_priorities = list(users[current_user].keys())

	priority_buttons = []

	for priority in available_priorities:
		callback_str = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.CHANGE_PRIORITY, priority)
		btn = InlineKeyboardButton(priority, callback_data=callback_str)
		if priority == current_priority:
			btn.text += CHECK_MARK_CHARACTER
			btn.callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SAVE)
		priority_buttons.append(btn)

	rows = utils.place_buttons_in_rows(priority_buttons)

	keyboard_markup = InlineKeyboardMarkup(rows)
	return keyboard_markup


def generate_cc_buttons(post_data: telebot.types.Message):
	main_channel_id = post_data.chat.id
	main_channel_id_str = str(main_channel_id)

	text, entities = utils.get_post_content(post_data)

	_, user_hashtag_indexes, _ = hashtag_utils.find_hashtag_indexes(text, entities, main_channel_id)

	if not user_hashtag_indexes:
		return

	user_tags = []
	for user_hashtag_index in user_hashtag_indexes:
		entity = entities[user_hashtag_index]
		user = text[entity.offset + 1:entity.offset + entity.length]
		user_tags.append(user)

	current_subchannel_user = user_tags[0]

	if main_channel_id_str not in SUBCHANNEL_DATA:
		return

	subchannel_buttons = []
	for user in SUBCHANNEL_DATA[main_channel_id_str]:
		if user == current_subchannel_user:
			continue
		callback_str = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.TOGGLE_CC, user)
		btn = InlineKeyboardButton("#" + user, callback_data=callback_str)
		if user in user_tags[1:]:
			btn.text += CHECK_MARK_CHARACTER

		subchannel_buttons.append(btn)

	rows = utils.place_buttons_in_rows(subchannel_buttons)

	keyboard_markup = InlineKeyboardMarkup(rows)
	return keyboard_markup


def get_subchannels_forwarding_data(main_channel_id):
	main_channel_id_str = str(main_channel_id)
	if main_channel_id_str not in SUBCHANNEL_DATA:
		return {}

	forwarding_data = {}

	channel_users = SUBCHANNEL_DATA[main_channel_id_str]
	for user in channel_users:
		user_priorities = channel_users[user]
		for priority in user_priorities:
			subchannel_id = user_priorities[priority]
			forwarding_data[user + " " + priority] = subchannel_id

	return forwarding_data


def add_control_buttons(bot: telebot.TeleBot, post_data: telebot.types.Message, hashtags: List[str]):
	keyboard_markup = generate_control_buttons(hashtags, post_data)
	utils.edit_message_keyboard(bot, post_data, keyboard_markup)


def handle_callback(bot: telebot.TeleBot, call: telebot.types.CallbackQuery):
	callback_type, other_data = utils.parse_callback_str(call.data)

	if callback_type == CB_TYPES.CHANGE_SUBCHANNEL:
		subchannel_name = other_data[0]
		change_subchannel_button_event(bot, call.message, subchannel_name)
	elif callback_type == CB_TYPES.CLOSE:
		change_state_button_event(bot, call.message, False)
	elif callback_type == CB_TYPES.OPEN:
		change_state_button_event(bot, call.message, True)
	elif callback_type == CB_TYPES.SAVE:
		forward_and_add_inline_keyboard(bot, call.message, force_forward=True)
	elif callback_type == CB_TYPES.SHOW_SUBCHANNELS:
		show_subchannel_buttons(bot, call.message)
	elif callback_type == CB_TYPES.SHOW_PRIORITIES:
		show_priority_buttons(bot, call.message)
	elif callback_type == CB_TYPES.CHANGE_PRIORITY:
		priority = other_data[0]
		change_priority_button_event(bot, call.message, priority)
	elif callback_type == CB_TYPES.SHOW_CC:
		show_cc_buttons(bot, call.message)
	elif callback_type == CB_TYPES.TOGGLE_CC:
		user = other_data[0]
		toggle_cc_button_event(bot, call.message, user)


def add_comment_to_ticket(bot: telebot.TeleBot, post_data: telebot.types.Message, text: str):
	main_message_id = post_data.message_id
	main_channel_id = post_data.chat.id
	comment_message_id = db_utils.get_discussion_message_id(main_message_id, main_channel_id)
	if comment_message_id:
		main_channel_id_str = str(main_channel_id)
		discussion_chat_id = DISCUSSION_CHAT_DATA[main_channel_id_str]
		bot.send_message(chat_id=discussion_chat_id, reply_to_message_id=comment_message_id, text=text)


def show_subchannel_buttons(bot: telebot.TeleBot, post_data: telebot.types.Message):
	subchannel_keyboard_markup = generate_subchannel_buttons(post_data)
	update_show_buttons(post_data, CB_TYPES.SHOW_SUBCHANNELS)
	post_data.reply_markup.keyboard += subchannel_keyboard_markup.keyboard

	utils.edit_message_keyboard(bot, post_data)


def show_priority_buttons(bot: telebot.TeleBot, post_data: telebot.types.Message):
	priority_keyboard_markup = generate_priority_buttons(post_data)
	update_show_buttons(post_data, CB_TYPES.SHOW_PRIORITIES)
	post_data.reply_markup.keyboard += priority_keyboard_markup.keyboard

	utils.edit_message_keyboard(bot, post_data)


def show_cc_buttons(bot: telebot.TeleBot, post_data: telebot.types.Message):
	cc_keyboard_markup = generate_cc_buttons(post_data)
	update_show_buttons(post_data, CB_TYPES.SHOW_CC)
	if cc_keyboard_markup:
		post_data.reply_markup.keyboard += cc_keyboard_markup.keyboard

	utils.edit_message_keyboard(bot, post_data)


def update_show_buttons(post_data: telebot.types.Message, current_button_type: str):
	main_channel_id = post_data.chat.id
	hashtags, _ = hashtag_utils.extract_hashtags(post_data, main_channel_id, False)
	control_buttons = generate_control_buttons(hashtags, post_data)
	post_data.reply_markup.keyboard = control_buttons.keyboard

	for button in post_data.reply_markup.keyboard[0]:
		if button.callback_data is None:
			continue
		cb_type, _ = utils.parse_callback_str(button.callback_data)
		if cb_type == current_button_type:
			button.callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SAVE)


def change_state_button_event(bot: telebot.TeleBot, post_data: telebot.types.Message, is_ticket_open: bool):
	main_channel_id = post_data.chat.id

	hashtags, post_data = hashtag_utils.extract_hashtags(post_data, main_channel_id)

	state_str = "opened" if is_ticket_open else "closed"
	add_comment_to_ticket(bot, post_data, f"The ticket was {state_str}.")

	hashtags[0] = hashtag_utils.OPENED_TAG if is_ticket_open else hashtag_utils.CLOSED_TAG

	rearrange_hashtags(bot, post_data, hashtags)
	for button in post_data.reply_markup.keyboard[0]:
		cb_type, _ = utils.parse_callback_str(button.callback_data)
		if cb_type == CB_TYPES.OPEN or cb_type == CB_TYPES.CLOSE:
			callback_type = CB_TYPES.CLOSE if is_ticket_open else CB_TYPES.OPEN
			button.callback_data = utils.create_callback_str(CALLBACK_PREFIX, callback_type)
			button.text = OPENED_TICKED_CHARACTER if is_ticket_open else CLOSED_TICKED_CHARACTER
			break
	utils.edit_message_keyboard(bot, post_data)
	forward_to_subchannel(bot, post_data, hashtags)


def change_subchannel_button_event(bot: telebot.TeleBot, post_data: telebot.types.Message, new_subchannel_name: str):
	main_channel_id = post_data.chat.id

	subchannel_user, subchannel_priority = new_subchannel_name.split(" ")

	original_post_data = copy.deepcopy(post_data)
	hashtags, post_data = hashtag_utils.extract_hashtags(post_data, main_channel_id)

	comment_text = ""
	if hashtags[1] != subchannel_user:
		comment_text += f"The ticket was reassigned to \"{subchannel_user}\". "
	if hashtags[-1] != subchannel_priority:
		comment_text += f"The priority was changed to {subchannel_priority}. "

	if comment_text:
		add_comment_to_ticket(bot, post_data, comment_text)

	if subchannel_user in hashtags[1:-1]:
		hashtags.remove(subchannel_user)

	hashtags.insert(1, subchannel_user)

	hashtags[-1] = hashtag_utils.PRIORITY_TAG + subchannel_priority

	rearrange_hashtags(bot, post_data, hashtags, original_post_data)
	add_control_buttons(bot, post_data, hashtags)
	forward_to_subchannel(bot, post_data, hashtags)


def change_priority_button_event(bot: telebot.TeleBot, post_data: telebot.types.Message, new_priority: str):
	main_channel_id = post_data.chat.id

	original_post_data = copy.deepcopy(post_data)
	hashtags, post_data = hashtag_utils.extract_hashtags(post_data, main_channel_id)

	add_comment_to_ticket(bot, post_data, f"The priority was changed to {new_priority}. ")
	hashtags[-1] = hashtag_utils.PRIORITY_TAG + new_priority

	rearrange_hashtags(bot, post_data, hashtags, original_post_data)
	add_control_buttons(bot, post_data, hashtags)
	forward_to_subchannel(bot, post_data, hashtags)


def toggle_cc_button_event(bot: telebot.TeleBot, post_data: telebot.types.Message, selected_user: str):
	main_channel_id = post_data.chat.id

	original_post_data = copy.deepcopy(post_data)
	hashtags, post_data = hashtag_utils.extract_hashtags(post_data, main_channel_id)

	if selected_user in hashtags:
		hashtags.remove(selected_user)
		add_comment_to_ticket(bot, post_data, f"User \"{selected_user}\" was removed from ticket's followers.")
	else:
		hashtags.insert(-1, selected_user)
		add_comment_to_ticket(bot, post_data, f"User \"{selected_user}\" was added to ticket's followers.")

	rearrange_hashtags(bot, post_data, hashtags, original_post_data)
	show_cc_buttons(bot, post_data)
	forward_to_subchannel(bot, post_data, hashtags)


def forward_and_add_inline_keyboard(bot: telebot.TeleBot, post_data: telebot.types.Message,
									use_default_user: bool = False, force_forward: bool = False):
	main_channel_id = post_data.chat.id

	original_post_data = copy.deepcopy(post_data)

	hashtags, post_data = hashtag_utils.extract_hashtags(post_data, main_channel_id)
	if hashtags[1] is None and hashtags[-1] is None and use_default_user:
		hashtags = hashtag_utils.insert_default_user_hashtags(main_channel_id, hashtags)

	rearrange_hashtags(bot, post_data, hashtags, original_post_data)
	add_control_buttons(bot, post_data, hashtags)
	if AUTO_FORWARDING_ENABLED or force_forward:
		forward_to_subchannel(bot, post_data, hashtags)


def rearrange_hashtags(bot: telebot.TeleBot, post_data: telebot.types.Message, hashtags: List[str],
					   original_post_data: telebot.types.Message = None):
	post_data = hashtag_utils.insert_hashtags(post_data, hashtags)

	if original_post_data and utils.is_post_data_equal(post_data, original_post_data):
		return

	try:
		text, entities = utils.get_post_content(post_data)
		utils.edit_message_content(bot, post_data, text=text, entities=entities, reply_markup=post_data.reply_markup)
	except ApiTelegramException as E:
		if E.error_code == 429:
			raise E
		logging.info(f"Exception during rearranging hashtags - {E}")
		return

