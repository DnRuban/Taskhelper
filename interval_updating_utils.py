import logging
import time

import telebot
from telebot.apihelper import ApiTelegramException

import config_utils
import utils
import db_utils
import forwarding_utils
import post_link_utils
import threading

from config_utils import DISCUSSION_CHAT_DATA, DELAY_AFTER_ONE_SCAN

UPDATE_STARTED_MSG_TEXT = "Started updating older posts. When update is complete this message will be deleted."

_INTERVAL_UPDATING_THREAD: threading.Thread = None
_UPDATE_STATUS: bool = False


def update_older_message(bot: telebot.TeleBot, main_channel_id: int, current_msg_id: int):
	try:
		forwarded_message = utils.get_main_message_content_by_id(bot, main_channel_id, current_msg_id)
	except ApiTelegramException:
		utils.delete_main_message(bot, main_channel_id, current_msg_id)
		return

	if forwarded_message is None:
		return

	if utils.get_forwarded_from_id(forwarded_message) != main_channel_id:
		return

	main_channel_message_id = forwarded_message.forward_from_message_id

	forwarded_message.message_id = main_channel_message_id
	forwarded_message.chat = forwarded_message.forward_from_chat

	updated_message = post_link_utils.update_post_link(bot, forwarded_message)

	if not updated_message:
		updated_message = forwarded_message

	forwarding_utils.forward_and_add_inline_keyboard(bot, updated_message)

	return main_channel_message_id


def store_discussion_message(bot: telebot.TeleBot, main_channel_id: int, current_msg_id: int, discussion_chat_id: int):
	forwarded_message = utils.get_message_content_by_id(bot, discussion_chat_id, current_msg_id)
	if forwarded_message is None:
		return

	forwarded_from_id = utils.get_forwarded_from_id(forwarded_message)
	if forwarded_from_id != main_channel_id:
		return

	main_channel_message_id = forwarded_message.forward_from_message_id
	if discussion_chat_id:
		db_utils.insert_or_update_discussion_message(main_channel_message_id, main_channel_id, current_msg_id)

	return main_channel_message_id


def start_interval_updating(bot: telebot.TeleBot, start_delay: int = 0):
	global _UPDATE_STATUS, _INTERVAL_UPDATING_THREAD

	if _UPDATE_STATUS:
		_UPDATE_STATUS = False
		_INTERVAL_UPDATING_THREAD.join()

	_UPDATE_STATUS = True
	_INTERVAL_UPDATING_THREAD = threading.Thread(target=interval_update_thread, args=(bot, start_delay,))
	_INTERVAL_UPDATING_THREAD.start()


def interval_update_thread(bot: telebot.TeleBot, start_delay: int = 0):
	start_time = time.time()
	last_update_time = 0
	while _UPDATE_STATUS:
		time.sleep(1)
		if (time.time() - start_time) < start_delay:
			continue
		if (time.time() - last_update_time) < (config_utils.UPDATE_INTERVAL * 60):
			continue

		update_in_progress_channel = db_utils.get_unfinished_update_channel()
		if update_in_progress_channel:
			main_channel_id, current_message_id = update_in_progress_channel
			main_channel_id_str = str(main_channel_id)

			discussion_chat_id = None
			if main_channel_id_str in DISCUSSION_CHAT_DATA:
				discussion_chat_id = DISCUSSION_CHAT_DATA[main_channel_id_str]

			check_all_messages(bot, main_channel_id, discussion_chat_id, current_message_id)

		finished_channels = db_utils.get_finished_update_channels()
		finished_channels = [c[0] for c in finished_channels]

		main_channel_ids = db_utils.get_main_channel_ids()
		for main_channel_id in main_channel_ids:
			if main_channel_id in finished_channels:
				continue
			main_channel_id_str = str(main_channel_id)

			discussion_chat_id = None
			if main_channel_id_str in DISCUSSION_CHAT_DATA:
				discussion_chat_id = DISCUSSION_CHAT_DATA[main_channel_id_str]

			check_all_messages(bot, main_channel_id, discussion_chat_id)

		logging.info("Interval check complete")
		db_utils.clear_updates_in_progress()
		if _UPDATE_STATUS and config_utils.HASHTAGS_BEFORE_UPDATE:
			config_utils.HASHTAGS_BEFORE_UPDATE = None
			config_utils.update_config({"HASHTAGS_BEFORE_UPDATE": None})
		last_update_time = time.time()


def check_all_messages(bot: telebot.TeleBot, main_channel_id: int, discussion_chat_id: int = None, start_from_message: int = None):
	if start_from_message and discussion_chat_id:
		current_msg_id = db_utils.get_discussion_message_id(start_from_message, main_channel_id)
		if current_msg_id is None:
			return
	elif discussion_chat_id:
		last_discussion_msg = utils.get_last_message(bot, discussion_chat_id)
		current_msg_id = last_discussion_msg
	else:
		current_msg_id = utils.get_last_message(bot, main_channel_id)

	last_updated_message_id = current_msg_id

	while current_msg_id > 0:
		time.sleep(DELAY_AFTER_ONE_SCAN)
		try:
			if not _UPDATE_STATUS:
				raise Exception("Interval update stop requested")
			if discussion_chat_id:
				main_channel_message_id = store_discussion_message(bot, main_channel_id, current_msg_id, discussion_chat_id)
				if not main_channel_message_id:
					main_channel_message_id = db_utils.get_main_from_discussion_message(current_msg_id, main_channel_id)
				if main_channel_message_id:
					update_older_message(bot, main_channel_id, main_channel_message_id)
					last_updated_message_id = main_channel_message_id
					db_utils.insert_or_update_channel_update_progress(main_channel_id, last_updated_message_id)
			else:
				update_older_message(bot, main_channel_id, current_msg_id)
				db_utils.insert_or_update_channel_update_progress(main_channel_id, current_msg_id)
		except ApiTelegramException as E:
			if E.error_code == 429:
				logging.warning(f"Too many requests - {E}")
				time.sleep(20)
				continue
			logging.error(f"Error during updating older messages - {E}")
		except Exception as E:
			logging.error(f"Updating older messages stopped because of exception - {E}")
			return

		current_msg_id -= 1
		if discussion_chat_id and current_msg_id <= 0:
			current_msg_id = last_updated_message_id
			discussion_chat_id = None
			logging.info(f"Checked all messages in discussion chat, last updated message id: {last_updated_message_id}")

	db_utils.insert_or_update_channel_update_progress(main_channel_id, 0)
	logging.info(f"Checked all messages in main channel - id: {main_channel_id}")

