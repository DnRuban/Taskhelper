import json
import logging
import threading
import time

import telebot.types

import channel_manager
import db_utils
import config_utils
import forwarding_utils
import interval_updating_utils
from hashtag_data import HashtagData

_DAILY_CHECK_INTERVAL = 60 * 60 * 24


def update_ticket_data(main_message_id: int, main_channel_id: int, hashtag_data: HashtagData):
	user_tags = hashtag_data.get_all_users()
	user_tags = ",".join(user_tags) if user_tags else None
	priority = hashtag_data.get_priority_number_or_default()
	is_ticket_opened = hashtag_data.is_opened()
	db_utils.insert_or_update_ticket_data(main_message_id, main_channel_id, is_ticket_opened, user_tags, priority)


def ticket_update_time_comparator(ticket):
	_, _, _, _, _, _, update_time, remind_time = ticket
	return max(update_time or 0, remind_time or 0)


def get_message_for_reminding(main_channel_id: int, user_id: int, user_tag: str):
	ticket_data = db_utils.get_tickets_for_reminding(main_channel_id, user_id, user_tag)
	if not ticket_data:
		logging.info(f"No tickets for reminding were found in {user_tag, main_channel_id}")
		return

	channel_ids = db_utils.get_user_individual_channels(main_channel_id, user_id)
	channel_data = {}
	for channel_id, settings in channel_ids:
		channel_data[channel_id] = json.loads(settings)

	filtered_ticket_data = []
	for ticket in ticket_data:
		copied_channel_id, copied_message_id, main_channel_id, main_message_id, ticket_user_tags, priority, _, _ = ticket
		if copied_channel_id not in channel_data:
			continue

		settings = channel_data[copied_channel_id]
		remind_settings = settings.get(channel_manager.SETTING_TYPES.REMIND)
		if not remind_settings:
			continue

		if channel_manager.REMIND_TYPES.ASSIGNED in remind_settings:
			if ticket_user_tags.startswith(user_tag):
				filtered_ticket_data.append(ticket)
				continue
		if channel_manager.REMIND_TYPES.FOLLOWED in remind_settings:
			user_tags = ticket_user_tags.split(",")
			if user_tag in user_tags[1:]:
				filtered_ticket_data.append(ticket)
				continue
		if channel_manager.REMIND_TYPES.REPORTED in remind_settings:
			sender_id = db_utils.get_main_message_sender(main_channel_id, main_message_id)
			if sender_id == user_id:
				filtered_ticket_data.append(ticket)
				continue

	highest_priority = 3
	for ticket in filtered_ticket_data:
		priority = int(ticket[5])
		if priority < highest_priority:
			highest_priority = priority

	filtered_ticket_data = list(filter(lambda ticket: int(ticket[5]) == highest_priority, filtered_ticket_data))

	if not filtered_ticket_data:
		logging.info(f"No forwarded tickets for reminding were found in {user_tag, main_channel_id}")
		return

	filtered_ticket_data.sort(key=ticket_update_time_comparator)
	copied_channel_id, copied_message_id, main_channel_id, main_message_id, _, _, _, _ = filtered_ticket_data[0]

	return main_message_id, copied_channel_id, copied_message_id


def send_daily_reminders(bot: telebot.TeleBot):
	user_data = db_utils.get_all_users()
	for user in user_data:
		main_channel_id, user_id, user_tag = user
		if not db_utils.is_user_reminder_data_exists(main_channel_id, user_tag):
			db_utils.insert_or_update_last_user_interaction(main_channel_id, user_tag, None)

		last_interaction_time = db_utils.get_last_interaction_time(main_channel_id, user_tag) or 0
		seconds_since_last_interaction = time.time() - last_interaction_time
		if seconds_since_last_interaction < config_utils.REMINDER_TIME_WITHOUT_INTERACTION * 60:
			continue

		message_to_remind = None
		while not message_to_remind:
			message_to_remind = get_message_for_reminding(main_channel_id, user_id, user_tag)
			if not message_to_remind:
				break
			message_id_to_remind, copied_channel_id, copied_message_id = message_to_remind

			forwarding_utils.delete_forwarded_message(bot, copied_channel_id, copied_message_id)
			interval_updating_utils.update_older_message(bot, main_channel_id, message_id_to_remind)
			new_message_id = db_utils.find_copied_message_in_channel(copied_channel_id, message_id_to_remind)
			if not new_message_id:
				logging.info(f"Tried to remind ticket {message_id_to_remind, main_channel_id}, but channel settings was changed.")
				message_to_remind = None

		if not message_to_remind:
			continue

		message_id_to_remind, _, _ = message_to_remind
		db_utils.insert_or_update_remind_time(message_id_to_remind, main_channel_id, user_tag, int(time.time()))
		logging.info(f"Sent reminder to {user_id, user_tag}, message: {message_id_to_remind, main_channel_id}.")


def start_reminder_thread(bot: telebot.TeleBot):
	threading.Thread(target=reminder_thread, args=(bot,)).start()


def reminder_thread(bot: telebot.TeleBot):
	while 1:
		if time.time() - config_utils.LAST_DAILY_REMINDER_TIME > _DAILY_CHECK_INTERVAL:
			send_daily_reminders(bot)
			config_utils.LAST_DAILY_REMINDER_TIME = int(time.time())
			config_utils.update_config({"LAST_DAILY_REMINDER_TIME": config_utils.LAST_DAILY_REMINDER_TIME})
		time.sleep(1)
