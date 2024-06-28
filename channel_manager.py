import json
from typing import List, Dict

import telebot
from telebot.apihelper import ApiTelegramException
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatMemberOwner

import config_utils
import db_utils
import forwarding_utils
import hashtag_data
import interval_updating_utils
import utils

CALLBACK_PREFIX = "CHNN"
NEW_USER_TYPE = "+"


class CB_TYPES:
	ASSIGNED_SELECTED = "AS"
	REPORTED_SELECTED = "CR"
	FOLLOWED_SELECTED = "FL"
	REMIND_SELECTED = "RMN"
	PRIORITY_SELECTED = "PR"
	DEFERRED_SELECTED = "DFR"
	DUE_SELECTED = "DUE"
	SAVE = "SV"
	TOGGLE_USER = "USR"
	TOGGLE_REMIND_SETTING = "TRM"
	SAVE_SELECTED_USERS = "SVU"
	SAVE_REMIND_SETTINGS = "SVR"
	SEND_CHANNEL_SETTINGS = "STT"
	NOP = "NOP"  # No operation


class SETTING_TYPES:
	ASSIGNED = "assigned"
	REPORTED = "reported"
	FOLLOWED = "cc"
	DUE = "due"
	DEFERRED = "deferred"
	REMIND = "remind"
	SETTINGS_MESSAGE_ID = "settings_message_id"


MENU_TITLES = {
	SETTING_TYPES.ASSIGNED: "Assigned to:",
	SETTING_TYPES.REPORTED: "Reported by:",
	SETTING_TYPES.FOLLOWED: "CCed to:",
	SETTING_TYPES.REMIND: "Remind me when:",
}


class REMIND_TYPES:
	ASSIGNED = "assigned"
	REPORTED = "reported"
	FOLLOWED = "cced"


_TOGGLE_CALLBACKS = [
	CB_TYPES.DUE_SELECTED,
	CB_TYPES.DEFERRED_SELECTED,
	CB_TYPES.PRIORITY_SELECTED,
	CB_TYPES.TOGGLE_USER,
	CB_TYPES.TOGGLE_REMIND_SETTING,
]

_TYPE_SEPARATOR = ","
_DEFAULT_SETTINGS = {
	SETTING_TYPES.DUE: True,
	SETTING_TYPES.DEFERRED: True,
	SETTING_TYPES.REMIND: [REMIND_TYPES.ASSIGNED],
}


def get_individual_channel_settings(channel_id: int):
	settings_str, priorities_str = db_utils.get_individual_channel_settings(channel_id)
	settings = json.loads(settings_str) if settings_str else {}
	priorities = priorities_str.split(",") if priorities_str else []
	return settings, priorities


def add_user_tags_to_button_text(button: InlineKeyboardButton, channel_type: str, settings: Dict):
	if channel_type not in settings:
		return

	user_tags = settings[channel_type]
	if len(user_tags) < 1:
		return

	if NEW_USER_TYPE in user_tags:
		user_tags.remove(NEW_USER_TYPE)
		user_tags.append("<new users>")

	button.text += f" {user_tags[0]}"
	for user_tag in user_tags[1:]:
		button.text += f", {user_tag}"


def generate_settings_keyboard(channel_id: int):
	settings, priorities = get_individual_channel_settings(channel_id)

	assigned_to_btn = InlineKeyboardButton("Assigned to:")
	assigned_to_btn.callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.ASSIGNED_SELECTED)
	add_user_tags_to_button_text(assigned_to_btn, SETTING_TYPES.ASSIGNED, settings)

	reported_by_btn = InlineKeyboardButton("Reported by:")
	reported_by_btn.callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.REPORTED_SELECTED)
	add_user_tags_to_button_text(reported_by_btn, SETTING_TYPES.REPORTED, settings)

	followed_by_btn = InlineKeyboardButton("CCed to:")
	followed_by_btn.callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.FOLLOWED_SELECTED)
	add_user_tags_to_button_text(followed_by_btn, SETTING_TYPES.FOLLOWED, settings)

	remind_btn = InlineKeyboardButton("Remind me when:")
	remind_settings = settings.get(SETTING_TYPES.REMIND)
	if remind_settings:
		settings_str = ",".join([f" {s}" for s in remind_settings])
		remind_btn.text += settings_str
	remind_btn.callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.REMIND_SELECTED)

	due_btn = InlineKeyboardButton("Due")
	due_btn.callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.DUE_SELECTED)
	is_due = settings[SETTING_TYPES.DUE] if SETTING_TYPES.DUE in settings else False
	due_btn.text += config_utils.BUTTON_TEXTS["CHECK"] if is_due else ""

	deferred_btn = InlineKeyboardButton("Deferred")
	deferred_btn.callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.DEFERRED_SELECTED)
	is_deferred = settings[SETTING_TYPES.DEFERRED] if SETTING_TYPES.DEFERRED in settings else False
	deferred_btn.text += config_utils.BUTTON_TEXTS["CHECK"] if is_deferred else ""

	buttons = [
		assigned_to_btn,
		reported_by_btn,
		followed_by_btn,
		remind_btn,
		due_btn,
		deferred_btn,
	]

	for priority in hashtag_data.POSSIBLE_PRIORITIES:
		priority_btn = InlineKeyboardButton(f"Priority {priority}")
		if priority in priorities:
			priority_btn.text += config_utils.BUTTON_TEXTS["CHECK"]
		priority_btn.callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.PRIORITY_SELECTED, priority)
		buttons.append(priority_btn)

	save_btn = InlineKeyboardButton(f"Save")
	save_btn.callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SAVE)
	buttons.append(save_btn)

	rows = [[btn] for btn in buttons]
	return InlineKeyboardMarkup(rows)


def send_settings_keyboard(bot: telebot.TeleBot, msg_data: telebot.types.Message):
	channel_id = msg_data.chat.id
	channel_admins = bot.get_chat_administrators(channel_id)

	channel_owner = next((user for user in channel_admins if type(user) == ChatMemberOwner), None)
	user_id = channel_owner.user.id
	main_channel_id = db_utils.get_main_channel_from_user(user_id)
	if not main_channel_id:
		bot.send_message(chat_id=channel_id, text="Can't recognize the user who called this command")
		return

	settings_str = json.dumps(_DEFAULT_SETTINGS)
	db_utils.insert_individual_channel(main_channel_id, channel_id, settings_str, user_id)

	settings, priorities = get_individual_channel_settings(channel_id)
	settings_message_id = settings.get(SETTING_TYPES.SETTINGS_MESSAGE_ID)
	if settings_message_id:
		forwarding_utils.delete_forwarded_message(bot, channel_id, settings_message_id)

	keyboard = generate_settings_keyboard(channel_id)
	text = '''
		Please select this channel's settings, click on buttons to select/deselect filtering parameters. When all needed parameters are selected press "Save" button. You can call this settings menu using "/show_settings" command. If "New users" parameter is selected than new users will be automatically added to the list. Descriptions of each parameter:
		1) Assigned to - include tickets that is assigned to the selected users
		2) Reported by - include tickets that is created by the selected users
		3) CCed to - include tickets where the selected users in CC
		4) Remind me when - regulates what tickets can be reminded in this channel
		5) Due - if this option is enabled, regular(NOT scheduled) tickets will be included in this channel
		6) Deferred - if this option is enabled, scheduled tickets will be included in this channel
	'''

	settings_message = bot.send_message(chat_id=channel_id, text=text, reply_markup=keyboard)
	settings[SETTING_TYPES.SETTINGS_MESSAGE_ID] = settings_message.id
	settings_str = json.dumps(settings)
	db_utils.update_individual_channel_settings(channel_id, settings_str)


def generate_user_keyboard(main_channel_id: int, channel_id: int, setting_type: str):
	settings, priorities = get_individual_channel_settings(channel_id)
	active_user_tags = []
	if setting_type in settings:
		active_user_tags = settings[setting_type]

	user_tags = db_utils.get_main_channel_user_tags(main_channel_id)

	nop_callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.NOP)
	text_button = InlineKeyboardButton(MENU_TITLES[setting_type], callback_data=nop_callback)
	buttons = [text_button]
	for user_tag in user_tags:
		callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.TOGGLE_USER, user_tag)
		button_text = f"#{user_tag}" if user_tag != NEW_USER_TYPE else "New users"
		user_button = InlineKeyboardButton(button_text, callback_data=callback)
		if user_tag in active_user_tags:
			user_button.text += config_utils.BUTTON_TEXTS["CHECK"]
		buttons.append(user_button)

	callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.TOGGLE_USER, NEW_USER_TYPE)
	new_user_button = InlineKeyboardButton(f"New users", callback_data=callback)
	if NEW_USER_TYPE in active_user_tags:
		new_user_button.text += config_utils.BUTTON_TEXTS["CHECK"]
	buttons.append(new_user_button)

	callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SAVE_SELECTED_USERS, setting_type)
	save_button = InlineKeyboardButton(f"Save", callback_data=callback)
	buttons.append(save_button)

	rows = [[btn] for btn in buttons]
	return InlineKeyboardMarkup(rows)


def open_user_selection(bot: telebot.TeleBot, call: CallbackQuery, setting_type: str):
	user_id = call.from_user.id
	main_channel_id = db_utils.get_main_channel_from_user(user_id)
	channel_id = call.message.chat.id

	keyboard = generate_user_keyboard(main_channel_id, channel_id, setting_type)
	bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.id, reply_markup=keyboard)


def generate_remind_keyboard(channel_id):
	settings, priorities = get_individual_channel_settings(channel_id)
	active_settings = []
	if SETTING_TYPES.REMIND in settings:
		active_settings = settings[SETTING_TYPES.REMIND]

	callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.TOGGLE_REMIND_SETTING, REMIND_TYPES.ASSIGNED)
	assigned_btn = InlineKeyboardButton(f"Assigned to me", callback_data=callback)
	if REMIND_TYPES.ASSIGNED in active_settings:
		assigned_btn.text += config_utils.BUTTON_TEXTS["CHECK"]

	callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.TOGGLE_REMIND_SETTING, REMIND_TYPES.REPORTED)
	reported_btn = InlineKeyboardButton(f"Reported by me", callback_data=callback)
	if REMIND_TYPES.REPORTED in active_settings:
		reported_btn.text += config_utils.BUTTON_TEXTS["CHECK"]

	callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.TOGGLE_REMIND_SETTING, REMIND_TYPES.FOLLOWED)
	followed_btn = InlineKeyboardButton(f"CCed to me", callback_data=callback)
	if REMIND_TYPES.FOLLOWED in active_settings:
		followed_btn.text += config_utils.BUTTON_TEXTS["CHECK"]

	callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SAVE_REMIND_SETTINGS)
	save_button = InlineKeyboardButton(f"Save", callback_data=callback)

	nop_callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.NOP)
	text_button = InlineKeyboardButton(MENU_TITLES[SETTING_TYPES.REMIND], callback_data=nop_callback)

	buttons = [
		text_button,
		assigned_btn,
		reported_btn,
		followed_btn,
		save_button,
	]

	rows = [[btn] for btn in buttons]
	return InlineKeyboardMarkup(rows)


def open_remind_selection(bot: telebot.TeleBot, call: CallbackQuery):
	channel_id = call.message.chat.id

	keyboard = generate_remind_keyboard(channel_id)
	bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.id, reply_markup=keyboard)


def toggle_user_button(bot: telebot.TeleBot, call: CallbackQuery, cb_type: str, cb_data: str):
	reply_markup = call.message.reply_markup
	buttons = [btn for row in reply_markup.keyboard for btn in row]
	for btn in buttons:
		callback_str = btn.callback_data
		btn_cb_type, btn_cb_data = utils.parse_callback_str(callback_str)
		if btn_cb_type == cb_type and btn_cb_data == cb_data:
			if btn.text.endswith(config_utils.BUTTON_TEXTS["CHECK"]):
				btn.text = btn.text[:-len(config_utils.BUTTON_TEXTS["CHECK"])]
			else:
				btn.text += config_utils.BUTTON_TEXTS["CHECK"]

	bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.id, reply_markup=reply_markup)


def save_user_settings(bot: telebot.TeleBot, call: CallbackQuery, setting_type: str):
	channel_id = call.message.chat.id
	settings, priorities = get_individual_channel_settings(channel_id)

	reply_markup = call.message.reply_markup
	buttons = [btn for row in reply_markup.keyboard for btn in row]
	selected_user_tags = []
	for btn in buttons:
		callback_str = btn.callback_data
		btn_cb_type, btn_cb_data = utils.parse_callback_str(callback_str)

		if btn_cb_type != CB_TYPES.TOGGLE_USER or not btn.text.endswith(config_utils.BUTTON_TEXTS["CHECK"]):
			continue

		user_tag, = btn_cb_data
		selected_user_tags.append(user_tag)

	settings[setting_type] = selected_user_tags
	settings_str = json.dumps(settings)
	db_utils.update_individual_channel_settings(channel_id, settings_str)

	keyboard = generate_settings_keyboard(channel_id)
	bot.edit_message_reply_markup(chat_id=channel_id, message_id=call.message.id, reply_markup=keyboard)


def save_remind_settings(bot: telebot.TeleBot, call: CallbackQuery):
	channel_id = call.message.chat.id
	settings, priorities = get_individual_channel_settings(channel_id)

	reply_markup = call.message.reply_markup
	buttons = [btn for row in reply_markup.keyboard for btn in row]
	selected_remind_settings = []
	for btn in buttons:
		callback_str = btn.callback_data
		btn_cb_type, btn_cb_data = utils.parse_callback_str(callback_str)

		if btn_cb_type != CB_TYPES.TOGGLE_REMIND_SETTING or not btn.text.endswith(config_utils.BUTTON_TEXTS["CHECK"]):
			continue

		setting_type, = btn_cb_data
		selected_remind_settings.append(setting_type)

	settings[SETTING_TYPES.REMIND] = selected_remind_settings
	settings_str = json.dumps(settings)
	db_utils.update_individual_channel_settings(channel_id, settings_str)

	keyboard = generate_settings_keyboard(channel_id)
	bot.edit_message_reply_markup(chat_id=channel_id, message_id=call.message.id, reply_markup=keyboard)


def handle_callback(bot: telebot.TeleBot, call: CallbackQuery):
	callback_type, other_data = utils.parse_callback_str(call.data)

	if callback_type == CB_TYPES.ASSIGNED_SELECTED:
		open_user_selection(bot, call, SETTING_TYPES.ASSIGNED)
	elif callback_type == CB_TYPES.REPORTED_SELECTED:
		open_user_selection(bot, call, SETTING_TYPES.REPORTED)
	elif callback_type == CB_TYPES.FOLLOWED_SELECTED:
		open_user_selection(bot, call, SETTING_TYPES.FOLLOWED)
	elif callback_type == CB_TYPES.REMIND_SELECTED:
		open_remind_selection(bot, call)
	elif callback_type == CB_TYPES.SAVE_SELECTED_USERS:
		setting_type, = other_data
		save_user_settings(bot, call, setting_type)
	elif callback_type == CB_TYPES.SAVE_REMIND_SETTINGS:
		save_remind_settings(bot, call)
	elif callback_type == CB_TYPES.SAVE:
		save_channel_settings(bot, call)
	elif callback_type == CB_TYPES.NOP:
		bot.answer_callback_query(call.id)
	elif callback_type in _TOGGLE_CALLBACKS:
		toggle_button(bot, call, callback_type, other_data)
	elif callback_type == CB_TYPES.SEND_CHANNEL_SETTINGS:
		send_settings_keyboard(bot, call.message)
		bot.answer_callback_query(call.id)


def is_button_checked(buttons: List[InlineKeyboardButton], target_cb_type: str):
	for btn in buttons:
		btn_cb_type, btn_cb_data = utils.parse_callback_str(btn.callback_data)
		if btn_cb_type == target_cb_type:
			return btn.text.endswith(config_utils.BUTTON_TEXTS["CHECK"])


def toggle_button(bot: telebot.TeleBot, call: CallbackQuery, cb_type: str, cb_data: str):
	reply_markup = call.message.reply_markup
	buttons = [btn for row in reply_markup.keyboard for btn in row]
	is_deferred_checked = is_button_checked(buttons, CB_TYPES.DEFERRED_SELECTED)
	is_due_checked = is_button_checked(buttons, CB_TYPES.DUE_SELECTED)

	for btn in buttons:
		callback_str = btn.callback_data
		btn_cb_type, btn_cb_data = utils.parse_callback_str(callback_str)

		if btn_cb_type != cb_type or btn_cb_data != cb_data:
			continue

		if btn.text.endswith(config_utils.BUTTON_TEXTS["CHECK"]):
			if (cb_type == CB_TYPES.DUE_SELECTED and not is_deferred_checked) or (cb_type == CB_TYPES.DEFERRED_SELECTED and not is_due_checked):
				bot.answer_callback_query(callback_query_id=call.id, text="At least one of the Due and Deferred buttons should be selected")
				return
			btn.text = btn.text[:-len(config_utils.BUTTON_TEXTS["CHECK"])]
		else:
			btn.text += config_utils.BUTTON_TEXTS["CHECK"]

	bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.id, reply_markup=reply_markup)


def save_channel_settings(bot: telebot.TeleBot, call: CallbackQuery):
	main_channel_id = db_utils.get_main_channel_from_user(call.from_user.id)
	if not main_channel_id and call.from_user.username:
		main_channel_id = db_utils.get_main_channel_from_user("@" + call.from_user.username)

	if not main_channel_id:
		bot.answer_callback_query(callback_query_id=call.id, text="User not found.")
		return

	reply_markup = call.message.reply_markup
	buttons = [btn for row in reply_markup.keyboard for btn in row]

	priorities = []
	new_settings = {
		SETTING_TYPES.DEFERRED: False,
		SETTING_TYPES.DUE: False,
	}

	for btn in buttons:
		callback_str = btn.callback_data
		btn_cb_type, btn_cb_data = utils.parse_callback_str(callback_str)
		if not btn.text.endswith(config_utils.BUTTON_TEXTS["CHECK"]) or btn_cb_type not in _TOGGLE_CALLBACKS:
			continue

		if btn_cb_type == CB_TYPES.PRIORITY_SELECTED:
			priority = btn_cb_data[0]
			priorities.append(priority)
		elif btn_cb_type == CB_TYPES.DEFERRED_SELECTED:
			new_settings[SETTING_TYPES.DEFERRED] = True
		elif btn_cb_type == CB_TYPES.DUE_SELECTED:
			new_settings[SETTING_TYPES.DUE] = True

	channel_id = call.message.chat.id
	settings, _ = get_individual_channel_settings(channel_id)
	for setting_name in new_settings:
		settings[setting_name] = new_settings[setting_name]

	priorities_str = _TYPE_SEPARATOR.join(priorities)
	settings.pop(SETTING_TYPES.SETTINGS_MESSAGE_ID, None)
	settings_str = json.dumps(settings)

	db_utils.update_individual_channel(channel_id, settings_str, priorities_str)

	forwarding_utils.delete_forwarded_message(bot, call.message.chat.id, call.message.id)

	interval_updating_utils.start_interval_updating(bot)


def add_new_user_tag_to_channels(main_channel_id: int, user_tag: str):
	channel_data = db_utils.get_all_individual_channels(main_channel_id)
	for channel in channel_data:
		channel_id, settings = channel
		settings = json.loads(settings)
		assigned = settings.get(SETTING_TYPES.ASSIGNED) or []
		reported = settings.get(SETTING_TYPES.REPORTED) or []
		followed = settings.get(SETTING_TYPES.FOLLOWED) or []

		if NEW_USER_TYPE in assigned:
			settings[SETTING_TYPES.ASSIGNED].append(user_tag)
		if NEW_USER_TYPE in reported:
			settings[SETTING_TYPES.REPORTED].append(user_tag)
		if NEW_USER_TYPE in followed:
			settings[SETTING_TYPES.FOLLOWED].append(user_tag)

		settings_str = json.dumps(settings)
		db_utils.update_individual_channel_settings(channel_id, settings_str)


def remove_user_tag_from_channels(main_channel_id: int, user_tag: str):
	channel_data = db_utils.get_all_individual_channels(main_channel_id)
	for channel in channel_data:
		channel_id, settings = channel
		settings = json.loads(settings)

		tag_filter = lambda t: t != user_tag
		for setting_type in [SETTING_TYPES.ASSIGNED, SETTING_TYPES.REPORTED, SETTING_TYPES.FOLLOWED]:
			if setting_type not in settings:
				continue
			settings[setting_type] = list(filter(tag_filter, settings[setting_type]))

		settings_str = json.dumps(settings)
		db_utils.update_individual_channel_settings(channel_id, settings_str)
