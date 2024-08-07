import calendar
import datetime
import logging
import threading
import time
from typing import List

import pytz
import telebot
from telebot.apihelper import ApiTelegramException
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

import config_utils
import db_utils
import forwarding_utils
import utils
from config_utils import TIMEZONE_NAME
from hashtag_data import HashtagData


class ScheduledMessageDispatcher:
	CALLBACK_PREFIX = "SCH"
	SCHEDULED_DATETIME_FORMAT = "%Y-%m-%d %H:%M"

	__scheduled_messages_list: list = []

	__MONTH_CALENDAR_CALLBACK = "CALENDAR"
	__SELECT_DAY_CALLBACK = "DAY"
	__NEXT_MONTH_CALLBACK = "NEXT"
	__PREVIOUS_MONTH_CALLBACK = "PREV"
	__SELECT_HOUR_CALLBACK = "HOUR"
	__SELECT_MINUTE_CALLBACK = "MIN"
	__SCHEDULE_MESSAGE_CALLBACK = "SCHEDULE"

	class ScheduledMessage:
		def __init__(self, main_message_id, main_channel_id, send_time):
			self.main_message_id = main_message_id
			self.main_channel_id = main_channel_id
			self.send_time = send_time

	def schedule_message(self, bot: telebot.TeleBot, call: telebot.types.CallbackQuery, send_time: int, dt: datetime.datetime):
		message = call.message
		main_message_id = message.message_id
		main_channel_id = message.chat.id

		if not db_utils.is_main_channel_exists(main_channel_id):
			return

		date_str = dt.strftime(self.SCHEDULED_DATETIME_FORMAT)

		if db_utils.is_message_scheduled(main_message_id, main_channel_id):
			db_utils.update_scheduled_message(main_message_id, main_channel_id, send_time)

			for msg in self.__scheduled_messages_list:
				if msg.main_message_id == main_message_id and msg.main_channel_id == main_channel_id:
					msg.send_time = send_time
			self.__scheduled_messages_list.sort(key=self.scheduled_message_comparison_func)

			comment_text = f"{call.from_user.first_name} rescheduled the ticket to be sent on {date_str}."
			utils.add_comment_to_ticket(bot, message, comment_text)

			hashtag_data = HashtagData(message, main_channel_id)
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

		hashtag_data = HashtagData(message, main_channel_id)
		message = hashtag_data.get_post_data_without_hashtags()

		hashtag_data.set_scheduled_tag(date_str)
		forwarding_utils.rearrange_hashtags(bot, message, hashtag_data)

		forwarding_utils.add_control_buttons(bot, message, hashtag_data)
		forwarding_utils.forward_to_subchannel(bot, message, hashtag_data)

		self.insert_schedule_message_info(main_message_id, main_channel_id, send_time)

	def insert_schedule_message_info(self, main_message_id, main_channel_id, send_time):
		scheduled_message_object = self.ScheduledMessage(main_message_id, main_channel_id, send_time)
		self.__scheduled_messages_list.append(scheduled_message_object)
		self.__scheduled_messages_list.sort(key=self.scheduled_message_comparison_func)

	def get_scheduled_messages_for_send(self):
		filtered_messages = []
		current_time = time.time()
		for msg in self.__scheduled_messages_list:
			if msg.send_time < current_time:
				filtered_messages.append(msg)
			else:
				break
		return filtered_messages

	def start_scheduled_thread(self, bot: telebot.TeleBot):
		scheduled_messages = db_utils.get_all_scheduled_messages()
		for msg in scheduled_messages:
			main_message_id, main_channel_id, send_time = msg
			self.insert_schedule_message_info(main_message_id, main_channel_id, send_time)
		self.__scheduled_messages_list.sort(key=self.scheduled_message_comparison_func)

		threading.Thread(target=self.schedule_loop_thread, args=(bot,)).start()

	def remove_scheduled_message(self, main_channel_id: int, main_message_id: int):
		for msg in self.__scheduled_messages_list:
			if msg.main_message_id == main_message_id and msg.main_channel_id == main_channel_id:
				self.__scheduled_messages_list.remove(msg)
		self.__scheduled_messages_list.sort(key=self.scheduled_message_comparison_func)

	def handle_callback(self, bot: telebot.TeleBot, call: telebot.types.CallbackQuery, current_channel_id: int = None, current_message_id: int = None):
		callback_type, other_data = utils.parse_callback_str(call.data)

		if callback_type == self.__MONTH_CALENDAR_CALLBACK:
			keyboard = self.generate_days_buttons()
			utils.edit_message_keyboard(bot, call.message, keyboard, chat_id=current_channel_id, message_id=current_message_id)
		elif callback_type == self.__SCHEDULE_MESSAGE_CALLBACK:
			self.schedule_message_event(bot, call, other_data)
		elif callback_type == self.__NEXT_MONTH_CALLBACK:
			self.change_month_event(bot, call.message, other_data, True, current_channel_id, current_message_id)
		elif callback_type == self.__PREVIOUS_MONTH_CALLBACK:
			self.change_month_event(bot, call.message, other_data, False, current_channel_id, current_message_id)
		elif callback_type == self.__SELECT_DAY_CALLBACK:
			self.select_day_event(bot, call.message, other_data, current_channel_id, current_message_id)
		elif callback_type == self.__SELECT_HOUR_CALLBACK:
			self.select_hour_event(bot, call.message, other_data, current_channel_id, current_message_id)

	def change_month_event(self, bot: telebot.TeleBot, msg_data: telebot.types.Message, args: list, forward: bool, current_channel_id: int = None, current_message_id: int = None):
		date_str = args[0]
		current_month, current_year = [int(num) for num in date_str.split(".")]
		current_month += 1 if forward else -1

		if current_month > 12:
			current_year += 1
			current_month = 1
		elif current_month < 1:
			current_year -= 1
			current_month = 12

		keyboard = self.generate_days_buttons([current_month, current_year])
		utils.edit_message_keyboard(bot, msg_data, keyboard, chat_id=current_channel_id, message_id=current_message_id)

	def select_day_event(self, bot: telebot.TeleBot, msg_data: telebot.types.Message, args: list, current_channel_id: int = None, current_message_id: int = None):
		current_date = args[0]
		keyboard = self.generate_hours_buttons(current_date)
		utils.edit_message_keyboard(bot, msg_data, keyboard, chat_id=current_channel_id, message_id=current_message_id)

	def select_hour_event(self, bot: telebot.TeleBot, msg_data: telebot.types.Message, args: list, current_channel_id: int = None, current_message_id: int = None):
		current_date, current_hour = args
		keyboard = self.generate_minutes_buttons(current_date, current_hour)
		utils.edit_message_keyboard(bot, msg_data, keyboard, chat_id=current_channel_id, message_id=current_message_id)

	def schedule_message_event(self, bot: telebot.TeleBot, call: telebot.types.CallbackQuery, args: list):
		date, hour, minute = args
		format_str = "%d.%m.%Y %H:%M"
		dt = datetime.datetime.strptime(f"{date} {hour}:{minute}", format_str)
		timezone = pytz.timezone(TIMEZONE_NAME)
		dt = timezone.localize(dt)
		send_time = int(dt.astimezone(pytz.UTC).timestamp())

		self.schedule_message(bot, call, send_time, dt)

	def generate_schedule_button(self):
		callback_data = utils.create_callback_str(self.CALLBACK_PREFIX, self.__MONTH_CALENDAR_CALLBACK)
		schedule_button_text = config_utils.BUTTON_TEXTS["SCHEDULE_MESSAGE"]
		schedule_button = InlineKeyboardButton(schedule_button_text, callback_data=callback_data)
		return schedule_button

	def generate_days_buttons(self, date_info=None):
		timezone = pytz.timezone(TIMEZONE_NAME)
		now = datetime.datetime.now(tz=timezone)

		if date_info:
			current_month, current_year = date_info
		else:
			current_year = now.year
			current_month = now.month

		current_date_str = f"{current_month}.{current_year}"

		left_arrow_cb = utils.create_callback_str(self.CALLBACK_PREFIX, self.__PREVIOUS_MONTH_CALLBACK, current_date_str)
		left_arrow_button = InlineKeyboardButton("<", callback_data=left_arrow_cb)

		right_arrow_cb = utils.create_callback_str(self.CALLBACK_PREFIX, self.__NEXT_MONTH_CALLBACK, current_date_str)
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
					callback = utils.create_callback_str(self.CALLBACK_PREFIX, self.__SELECT_DAY_CALLBACK, f"{day}.{current_date_str}")

				day_button = InlineKeyboardButton(button_text, callback_data=callback)
				week_buttons.append(day_button)
			keyboard_rows.append(week_buttons)

		return InlineKeyboardMarkup(keyboard_rows)

	def generate_hours_buttons(self, current_date):
		back_button_callback = utils.create_callback_str(self.CALLBACK_PREFIX, self.__MONTH_CALENDAR_CALLBACK)
		back_button = InlineKeyboardButton("Back", callback_data=back_button_callback)

		keyboard_rows = [[back_button]]
		width = 4
		height = 6

		for i in range(height):
			buttons_row = []
			for j in range(width):
				hour = i * width + j
				hour = str(hour).zfill(2)
				callback = utils.create_callback_str(self.CALLBACK_PREFIX, self.__SELECT_HOUR_CALLBACK, current_date, hour)
				button = InlineKeyboardButton(f"{hour}:00", callback_data=callback)
				buttons_row.append(button)

			keyboard_rows.append(buttons_row)

		return InlineKeyboardMarkup(keyboard_rows)

	def generate_minutes_buttons(self, current_date, current_hour):
		back_button_callback = utils.create_callback_str(self.CALLBACK_PREFIX, self.__SELECT_DAY_CALLBACK, current_date)
		back_button = InlineKeyboardButton("Back", callback_data=back_button_callback)

		keyboard_rows = [[back_button]]
		width = 2
		height = 6

		for i in range(height):
			buttons_row = []
			for j in range(width):
				minute = (i * width + j) * 5
				minute = str(minute).zfill(2)
				callback = utils.create_callback_str(self.CALLBACK_PREFIX, self.__SCHEDULE_MESSAGE_CALLBACK, current_date, current_hour, minute)
				button = InlineKeyboardButton(f"{current_hour}:{minute}", callback_data=callback)
				buttons_row.append(button)

			keyboard_rows.append(buttons_row)

		return InlineKeyboardMarkup(keyboard_rows)

	def send_scheduled_message(self, bot: telebot.TeleBot, scheduled_message: ScheduledMessage):
		main_message_id = scheduled_message.main_message_id
		main_channel_id = scheduled_message.main_channel_id
		logging.info(f"Sending scheduled message {main_message_id, main_channel_id, scheduled_message.send_time}")
		try:
			message = utils.get_main_message_content_by_id(bot, main_channel_id, main_message_id)
		except ApiTelegramException:
			utils.delete_main_message(bot, main_channel_id, main_message_id)
			self.__scheduled_messages_list.remove(scheduled_message)
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
		self.remove_scheduled_message(main_channel_id, main_message_id)

	def update_scheduled_message_status(self, post_data: telebot.types.Message):
		main_channel_id = post_data.chat.id
		main_message_id = post_data.message_id
		if db_utils.get_scheduled_message_send_time(main_message_id, main_channel_id) is not None:
			db_utils.delete_scheduled_message_main(main_message_id, main_channel_id)
			self.remove_scheduled_message(main_channel_id, main_message_id)

	def schedule_loop_thread(self, bot: telebot.TeleBot):
		while 1:
			for_send = self.get_scheduled_messages_for_send()
			for msg_info in for_send:
				try:
					self.send_scheduled_message(bot, msg_info)
				except Exception as E:
					logging.error(f"Exception during sending scheduled message: {E}")
			time.sleep(1)

	def update_scheduled_message_tags(self, hashtag_data: HashtagData):
		if not hashtag_data.is_scheduled():
			return

		dt = datetime.datetime.strptime(hashtag_data.get_scheduled_datetime_str(), self.SCHEDULED_DATETIME_FORMAT)
		timezone = pytz.timezone(TIMEZONE_NAME)
		dt = timezone.localize(dt)
		is_sent = datetime.datetime.now().timestamp() > dt.timestamp()
		hashtag_data.set_scheduled_status(is_sent)

	def update_scheduled_time_from_ticket(self, msg_data: telebot.types.Message, hashtag_data: HashtagData):
		main_channel_id = msg_data.chat.id
		main_message_id = msg_data.message_id

		if not hashtag_data.is_scheduled():
			db_utils.delete_scheduled_message_main(main_message_id, main_channel_id)
			self.remove_scheduled_message(main_channel_id, main_message_id)
			return

		datetime_str = hashtag_data.get_scheduled_datetime_str()
		dt = datetime.datetime.strptime(datetime_str, self.SCHEDULED_DATETIME_FORMAT)

		timezone = pytz.timezone(TIMEZONE_NAME)
		dt = timezone.localize(dt)
		tag_send_time = int(dt.astimezone(pytz.UTC).timestamp())

		if not db_utils.is_message_scheduled(main_message_id, main_channel_id):
			db_utils.insert_scheduled_message(main_message_id, main_channel_id, 0, 0, tag_send_time)
			self.insert_schedule_message_info(main_message_id, main_channel_id, tag_send_time)
			return

		ticket_send_time = db_utils.get_scheduled_message_send_time(main_message_id, main_channel_id)
		if ticket_send_time != tag_send_time:
			db_utils.update_scheduled_message(main_message_id, main_channel_id, tag_send_time)

			for msg in self.__scheduled_messages_list:
				if msg.main_message_id == main_message_id and msg.main_channel_id == main_channel_id:
					msg.send_time = tag_send_time
			self.__scheduled_messages_list.sort(key=self.scheduled_message_comparison_func)

	@staticmethod
	def scheduled_message_comparison_func(msg: ScheduledMessage):
		return msg.send_time


scheduled_message_dispatcher = ScheduledMessageDispatcher()