import calendar
import datetime
import logging
import threading
import time
from typing import List

import pytz
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

import config_utils
import db_utils
import forwarding_utils
import utils
from config_utils import TIMEZONE_NAME
from hashtag_data import HashtagData
from utils import SCHEDULED_DATETIME_FORMAT

CALLBACK_PREFIX = "SCH"

SCHEDULED_MESSAGES_LIST: list = []


class CB_TYPES:
	MONTH_CALENDAR = "CALENDAR"
	SELECT_DAY = "DAY"
	NEXT_MONTH = "NEXT"
	PREVIOUS_MONTH = "PREV"
	SELECT_HOUR = "HOUR"
	SELECT_MINUTE = "MIN"
	SCHEDULE_MESSAGE = "SCHEDULE"


def schedule_message(bot: telebot.TeleBot, call: telebot.types.CallbackQuery, send_time: int, dt: datetime.datetime):
	message = call.message
	main_message_id = message.message_id
	main_channel_id = message.chat.id

	if not db_utils.is_main_channel_exists(main_channel_id):
		return

	date_str = dt.strftime(SCHEDULED_DATETIME_FORMAT)
	hashtag_data = HashtagData(message, main_channel_id)
	other_tags_date_str = hashtag_data.find_scheduled_tag_in_other_hashtags()

	if other_tags_date_str:
		scheduled_date = datetime.datetime.strptime(date_str, SCHEDULED_DATETIME_FORMAT)
		current_timestamp = scheduled_date.timestamp()
		other_tags_date = datetime.datetime.strptime(other_tags_date_str, SCHEDULED_DATETIME_FORMAT)
		other_tags_timestamp = other_tags_date.timestamp()

		if current_timestamp > other_tags_timestamp:
			bot.answer_callback_query(call.id, "Scheduled tag with earlier date is already present in the text")
			return

	if db_utils.is_message_scheduled(main_message_id, main_channel_id):
		db_utils.update_scheduled_message(main_message_id, main_channel_id, send_time)

		for msg in SCHEDULED_MESSAGES_LIST:
			message_id, channel_id, _ = msg
			if message_id == main_message_id and channel_id == main_channel_id:
				msg[2] = send_time
		SCHEDULED_MESSAGES_LIST.sort(key=scheduled_message_comparison_func)

		comment_text = f"{call.from_user.first_name} rescheduled the ticket to be sent on {date_str}."
		utils.add_comment_to_ticket(bot, message, comment_text)

		message = hashtag_data.get_post_data_without_hashtags()

		hashtag_data.set_scheduled_tag(date_str)
		forwarding_utils.rearrange_hashtags(bot, message, hashtag_data)

		forwarding_utils.add_control_buttons(bot, message, hashtag_data)
		forwarding_utils.forward_to_subchannel(bot, message, hashtag_data)

		return

	if send_time <= 0:
		return

	comment_text = f"{call.from_user.first_name} scheduled the ticket to be sent on {date_str}."
	utils.add_comment_to_ticket(bot, message, comment_text)

	db_utils.insert_scheduled_message(main_message_id, main_channel_id, 0, 0, send_time)

	message = hashtag_data.get_post_data_without_hashtags()

	hashtag_data.set_scheduled_tag(date_str)
	forwarding_utils.rearrange_hashtags(bot, message, hashtag_data)

	forwarding_utils.add_control_buttons(bot, message, hashtag_data)
	forwarding_utils.forward_to_subchannel(bot, message, hashtag_data)

	scheduled_info = [main_message_id, main_channel_id, send_time]
	insert_schedule_message_info(scheduled_info)


def insert_schedule_message_info(scheduled_info):
	SCHEDULED_MESSAGES_LIST.append(scheduled_info)
	SCHEDULED_MESSAGES_LIST.sort(key=scheduled_message_comparison_func)


def handle_callback(bot: telebot.TeleBot, call: telebot.types.CallbackQuery, current_channel_id: int = None, current_message_id: int = None):
	callback_type, other_data = utils.parse_callback_str(call.data)

	if callback_type == CB_TYPES.MONTH_CALENDAR:
		keyboard = generate_days_buttons()
		utils.edit_message_keyboard(bot, call.message, keyboard, chat_id=current_channel_id, message_id=current_message_id)
	elif callback_type == CB_TYPES.SCHEDULE_MESSAGE:
		schedule_message_event(bot, call, other_data)
	elif callback_type == CB_TYPES.NEXT_MONTH:
		change_month_event(bot, call.message, other_data, True, current_channel_id, current_message_id)
	elif callback_type == CB_TYPES.PREVIOUS_MONTH:
		change_month_event(bot, call.message, other_data, False, current_channel_id, current_message_id)
	elif callback_type == CB_TYPES.SELECT_DAY:
		select_day_event(bot, call.message, other_data, current_channel_id, current_message_id)
	elif callback_type == CB_TYPES.SELECT_HOUR:
		select_hour_event(bot, call.message, other_data, current_channel_id, current_message_id)


def change_month_event(bot: telebot.TeleBot, msg_data: telebot.types.Message, args: list, forward: bool, current_channel_id: int = None, current_message_id: int = None):
	date_str = args[0]
	current_month, current_year = [int(num) for num in date_str.split(".")]
	current_month += 1 if forward else -1

	if current_month > 12:
		current_year += 1
		current_month = 1
	elif current_month < 1:
		current_year -= 1
		current_month = 12

	keyboard = generate_days_buttons([current_month, current_year])
	utils.edit_message_keyboard(bot, msg_data, keyboard, chat_id=current_channel_id, message_id=current_message_id)


def select_day_event(bot: telebot.TeleBot, msg_data: telebot.types.Message, args: list, current_channel_id: int = None, current_message_id: int = None):
	current_date = args[0]
	keyboard = generate_hours_buttons(current_date)
	utils.edit_message_keyboard(bot, msg_data, keyboard, chat_id=current_channel_id, message_id=current_message_id)


def select_hour_event(bot: telebot.TeleBot, msg_data: telebot.types.Message, args: list, current_channel_id: int = None, current_message_id: int = None):
	current_date, current_hour = args
	keyboard = generate_minutes_buttons(current_date, current_hour)
	utils.edit_message_keyboard(bot, msg_data, keyboard, chat_id=current_channel_id, message_id=current_message_id)


def schedule_message_event(bot: telebot.TeleBot, call: telebot.types.CallbackQuery, args: list):
	date, hour, minute = args
	format_str = "%d.%m.%Y %H:%M"
	dt = datetime.datetime.strptime(f"{date} {hour}:{minute}", format_str)
	timezone = pytz.timezone(TIMEZONE_NAME)
	dt = timezone.localize(dt)
	send_time = int(dt.astimezone(pytz.UTC).timestamp())

	schedule_message(bot, call, send_time, dt)


def generate_schedule_button():
	callback_data = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.MONTH_CALENDAR)
	schedule_button_text = config_utils.BUTTON_TEXTS["SCHEDULE_MESSAGE"]
	schedule_button = InlineKeyboardButton(schedule_button_text, callback_data=callback_data)
	return schedule_button


def generate_days_buttons(date_info=None):
	timezone = pytz.timezone(TIMEZONE_NAME)
	now = datetime.datetime.now(tz=timezone)

	if date_info:
		current_month, current_year = date_info
	else:
		current_year = now.year
		current_month = now.month

	current_date_str = f"{current_month}.{current_year}"

	left_arrow_cb = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.PREVIOUS_MONTH, current_date_str)
	left_arrow_button = InlineKeyboardButton("<", callback_data=left_arrow_cb)

	right_arrow_cb = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.NEXT_MONTH, current_date_str)
	right_arrow_button = InlineKeyboardButton(">", callback_data=right_arrow_cb)

	current_month_button = InlineKeyboardButton(f"{current_year} {calendar.month_name[current_month]}", callback_data="_")

	back_button_callback = utils.create_callback_str(forwarding_utils.CALLBACK_PREFIX, forwarding_utils.CB_TYPES.SAVE)
	back_button = InlineKeyboardButton("Back", callback_data=back_button_callback)

	keyboard_rows = [[back_button]]
	keyboard_rows += [[left_arrow_button, current_month_button, right_arrow_button]]

	month_list = calendar.monthcalendar(current_year, current_month)
	for week in month_list:
		week_buttons = []
		for day in week:
			button_text = str(day) if day > 0 else " "
			if now.day == day and now.month == current_month and now.year == current_year:
				button_text = config_utils.BUTTON_TEXTS["CHECK"] + button_text
			callback = "_"
			if day > 0:
				callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SELECT_DAY, f"{day}.{current_date_str}")

			day_button = InlineKeyboardButton(button_text, callback_data=callback)
			week_buttons.append(day_button)
		keyboard_rows.append(week_buttons)

	return InlineKeyboardMarkup(keyboard_rows)


def generate_hours_buttons(current_date):
	back_button_callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.MONTH_CALENDAR)
	back_button = InlineKeyboardButton("Back", callback_data=back_button_callback)

	keyboard_rows = [[back_button]]
	width = 4
	height = 6

	for i in range(height):
		buttons_row = []
		for j in range(width):
			hour = i * width + j
			hour = str(hour).zfill(2)
			callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SELECT_HOUR, current_date, hour)
			button = InlineKeyboardButton(f"{hour}:00", callback_data=callback)
			buttons_row.append(button)

		keyboard_rows.append(buttons_row)

	return InlineKeyboardMarkup(keyboard_rows)


def generate_minutes_buttons(current_date, current_hour):
	back_button_callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SELECT_DAY, current_date)
	back_button = InlineKeyboardButton("Back", callback_data=back_button_callback)

	keyboard_rows = [[back_button]]
	width = 2
	height = 6

	for i in range(height):
		buttons_row = []
		for j in range(width):
			minute = (i * width + j) * 5
			minute = str(minute).zfill(2)
			callback = utils.create_callback_str(CALLBACK_PREFIX, CB_TYPES.SCHEDULE_MESSAGE, current_date, current_hour, minute)
			button = InlineKeyboardButton(f"{current_hour}:{minute}", callback_data=callback)
			buttons_row.append(button)

		keyboard_rows.append(buttons_row)

	return InlineKeyboardMarkup(keyboard_rows)


def send_scheduled_message(bot: telebot.TeleBot, scheduled_message_info: List):
	logging.info(f"Sending scheduled message {scheduled_message_info}")
	main_message_id, main_channel_id, send_time = scheduled_message_info
	message = utils.get_message_content_by_id(bot, main_channel_id, main_message_id)
	if message is None:
		return

	message.message_id = main_message_id
	message.chat.id = main_channel_id

	hashtag_data = HashtagData(message, main_channel_id)
	post_data = hashtag_data.get_post_data_without_hashtags()

	forwarding_utils.rearrange_hashtags(bot, post_data, hashtag_data)
	forwarding_utils.add_control_buttons(bot, post_data, hashtag_data)
	forwarding_utils.forward_to_subchannel(bot, post_data, hashtag_data)

	current_time = int(time.time())
	db_utils.insert_or_update_sent_scheduled_message(main_message_id, main_channel_id, current_time)
	db_utils.delete_scheduled_message_main(main_message_id, main_channel_id)
	remove_scheduled_message(main_channel_id, main_message_id)


def remove_scheduled_message(main_channel_id: int, main_message_id: int):
	for scheduled_message in SCHEDULED_MESSAGES_LIST:
		message_id, channel_id, _ = scheduled_message
		if message_id == main_message_id and channel_id == main_channel_id:
			SCHEDULED_MESSAGES_LIST.remove(scheduled_message)
	SCHEDULED_MESSAGES_LIST.sort(key=scheduled_message_comparison_func)


def update_scheduled_message_status(post_data: telebot.types.Message):
	main_channel_id = post_data.chat.id
	main_message_id = post_data.message_id
	if db_utils.get_scheduled_message_send_time(main_message_id, main_channel_id) is not None:
		db_utils.delete_scheduled_message_main(main_message_id, main_channel_id)
		remove_scheduled_message(main_channel_id, main_message_id)


def scheduled_message_comparison_func(msg):
	send_time = msg[2]
	return send_time


def get_scheduled_messages_for_send():
	filtered_messages = []
	current_time = time.time()
	for msg in SCHEDULED_MESSAGES_LIST:
		if msg[2] < current_time:
			filtered_messages.append(msg)
		else:
			break
	return filtered_messages


def start_scheduled_thread(bot: telebot.TeleBot):
	scheduled_messages = db_utils.get_all_scheduled_messages()
	for m in scheduled_messages:
		main_message_id, main_channel_id, send_time = m
		SCHEDULED_MESSAGES_LIST.append([main_message_id, main_channel_id, send_time])
	SCHEDULED_MESSAGES_LIST.sort(key=scheduled_message_comparison_func)

	threading.Thread(target=schedule_loop_thread, args=(bot,)).start()


def schedule_loop_thread(bot: telebot.TeleBot):
	while 1:
		for_send = get_scheduled_messages_for_send()
		for msg_info in for_send:
			try:
				send_scheduled_message(bot, msg_info)
			except Exception as E:
				logging.error(f"Exception during sending scheduled message: {E}")
		time.sleep(1)


def update_scheduled_time_from_ticket(bot: telebot.TeleBot, msg_data: telebot.types.Message, hashtag_data: HashtagData):
	main_channel_id = msg_data.chat.id
	main_message_id = msg_data.message_id

	if not hashtag_data.is_scheduled():
		db_utils.delete_scheduled_message_main(main_message_id, main_channel_id)
		remove_scheduled_message(main_channel_id, main_message_id)
		return

	datetime_str = hashtag_data.get_scheduled_datetime()
	dt = datetime.datetime.strptime(datetime_str, SCHEDULED_DATETIME_FORMAT)

	timezone = pytz.timezone(TIMEZONE_NAME)
	dt = timezone.localize(dt)
	tag_send_time = int(dt.astimezone(pytz.UTC).timestamp())

	if not db_utils.is_message_scheduled(main_message_id, main_channel_id):
		db_utils.insert_scheduled_message(main_message_id, main_channel_id, 0, 0, tag_send_time)
		scheduled_info = [main_message_id, main_channel_id, tag_send_time]
		insert_schedule_message_info(scheduled_info)
		comment_text = f"Ticket was scheduled to be sent on {datetime_str}."
		utils.add_comment_to_ticket(bot, msg_data, comment_text)
		return

	ticket_send_time = db_utils.get_scheduled_message_send_time(main_message_id, main_channel_id)
	if ticket_send_time != tag_send_time:
		db_utils.update_scheduled_message(main_message_id, main_channel_id, tag_send_time)

		for msg in SCHEDULED_MESSAGES_LIST:
			message_id, channel_id, _ = msg
			if message_id == main_message_id and channel_id == main_channel_id:
				msg[2] = tag_send_time
		SCHEDULED_MESSAGES_LIST.sort(key=scheduled_message_comparison_func)

		comment_text = f"Ticket was rescheduled to {datetime_str}."
		utils.add_comment_to_ticket(bot, msg_data, comment_text)
