import copy

import pytz
import telebot

import channel_manager
import config_utils
import core_api
import db_utils
import forwarding_utils
import hashtag_data
import interval_updating_utils
import user_utils
import utils
from scheduled_messages_utils import scheduled_message_dispatcher


def initialize_bot_commands(bot: telebot.TeleBot):
	commands = []
	for command in COMMAND_LIST:
		command_text, description, _ = command
		commands.append(telebot.types.BotCommand(command_text, description))
	bot.set_my_commands(commands, telebot.types.BotCommandScopeAllPrivateChats())


def handle_channel_command(bot: telebot.TeleBot, msg_data: telebot.types.Message):
	command_parts = msg_data.text.split(" ")
	command_parts = [p for p in command_parts if p]
	command = command_parts[0]
	arguments = command_parts[1:]

	if command == "/show_settings" or command == "/start":
		forwarding_utils.delete_forwarded_message(bot, msg_data.chat.id, msg_data.message_id)
		channel_manager.initialize_channel(bot, msg_data.chat.id)
	elif command == "/set_channel_hashtag":
		if len(arguments) != 1:
			bot.send_message(chat_id=msg_data.chat.id, text="You should specify only one hashtag.")
			return
		hashtag = arguments[0]
		if not hashtag.startswith("#"):
			bot.send_message(chat_id=msg_data.chat.id, text="You should specify hashtag with '#' symbol.")
			return

		db_utils.insert_or_update_custom_hashtag(msg_data.chat.id, hashtag)
		bot.send_message(chat_id=msg_data.chat.id, text="Hashtag successfully changed.")
	elif command == "/remove_channel_hashtag":
		db_utils.insert_or_update_custom_hashtag(msg_data.chat.id, None)
		bot.send_message(chat_id=msg_data.chat.id, text="Hashtag successfully removed.")


def handle_command(bot: telebot.TeleBot, msg_data: telebot.types.Message):
	text = msg_data.text
	for command in COMMAND_LIST:
		command_text, _, handler = command
		if text.startswith(command_text):
			command_end_pos = text.find(" ")
			arguments = text[command_end_pos + 1:]
			return handler(bot, msg_data, arguments)


def handle_help_command(bot: telebot.TeleBot, msg_data: telebot.types.Message, arguments: str):
	help_text = ""
	help_text += "/set_dump_chat_id <CHAT_ID> — changes dump chat id\n\n"
	help_text += "/set_interval_check_time <MINUTES> — changes delay between interval checks\n\n"
	help_text += "/add_main_channel <CHANNEL_ID> — add main channel\n\n"
	help_text += "/remove_main_channel <CHANNEL_ID> — remove main channel\n\n"
	help_text += "/enable_auto_forwarding — enables auto forwarding tickets found during scanning\n\n"
	help_text += "/disable_auto_forwarding — disables auto forwarding tickets found during scanning\n\n"

	help_text += "/set_timezone <TIMEZONE> — changes timezone identifier\n"
	help_text += "Example: /set_timezone Europe/Kiev\n\n"
	help_text += "/set_user_tag <MAIN_CHANNEL_ID> <TAG> <USERNAME_OR_USER_ID> — add or change username or user id of the tag\n"
	help_text += "Example with username: /set_user_tag -100987987987 aa @username\n"
	help_text += "Example with user id: /set_user_tag -100987987987 aa 321123321\n\n"
	help_text += "/remove_user_tag <MAIN_CHANNEL_ID> <TAG> — remove user assigned to specified tag\n"
	help_text += "Example with username: /remove_user_tag -100987987987 aa\n\n"
	help_text += "/set_default_subchannel <MAIN_CHANNEL_ID> <DEFAULT_USER_TAG> <DEFAULT_PRIORITY> — changes default subchannel\n"
	help_text += "Example: /set_default_subchannel -100987987987 aa 1\n\n"
	help_text += "/set_button_text <BUTTON_NAME> <NEW_VALUE> — changes storage channel for scheduled messages\n"
	help_text += "Available buttons: opened, closed, assigned, cc, schedule, check, priority\n"
	help_text += "Example: /set_button_text opened Op\n\n"
	help_text += "/set_hashtag_text <HASHTAG_NAME> <NEW_VALUE> — changes storage channel for scheduled messages\n"
	help_text += "Available hashtags: opened, closed, scheduled, priority\n"
	help_text += "Example: /set_hashtag_text opened Op\n\n"
	help_text += "/set_remind_without_interaction <MINUTES> — changes timeout for skipping daily reminder if user is interacted with tickets within this time\n"
	help_text += "Example: /set_remind_without_interaction 1440\n\n"
	bot.send_message(chat_id=msg_data.chat.id, text=help_text)


def handle_set_dump_chat_id(bot: telebot.TeleBot, msg_data: telebot.types.Message, arguments: str):
	try:
		dump_chat_id = int(arguments)
	except ValueError:
		bot.send_message(chat_id=msg_data.chat.id, text="You need to specify chat id.")
		return
	config_utils.DUMP_CHAT_ID = dump_chat_id
	bot.send_message(chat_id=msg_data.chat.id, text="Dump chat id successfully changed.")
	config_utils.update_config({"DUMP_CHAT_ID": config_utils.DUMP_CHAT_ID})


def handle_set_interval_check(bot: telebot.TeleBot, msg_data: telebot.types.Message, arguments: str):
	try:
		interval = int(arguments)
	except ValueError:
		bot.send_message(chat_id=msg_data.chat.id, text="You need to specify number of seconds.")
		return
	config_utils.UPDATE_INTERVAL = interval
	bot.send_message(chat_id=msg_data.chat.id, text="Interval successfully changed.")
	config_utils.update_config({"UPDATE_INTERVAL": config_utils.UPDATE_INTERVAL})


def handle_set_timezone(bot: telebot.TeleBot, msg_data: telebot.types.Message, arguments: str):
	try:
		new_timezone = pytz.timezone(arguments)
	except pytz.exceptions.UnknownTimeZoneError:
		bot.send_message(chat_id=msg_data.chat.id, text="Wrong timezone identifier.")
		return

	current_timezone = pytz.timezone(config_utils.TIMEZONE_NAME)
	scheduled_message_dispatcher.update_timezone(current_timezone, new_timezone)

	config_utils.TIMEZONE_NAME = arguments
	bot.send_message(chat_id=msg_data.chat.id, text="Timezone successfully changed.")
	config_utils.update_config({"TIMEZONE_NAME": config_utils.TIMEZONE_NAME})

	interval_updating_utils.start_interval_updating(bot)


def handle_main_channel_change(bot: telebot.TeleBot, msg_data: telebot.types.Message, arguments: str):
	try:
		channel_id = int(arguments)
	except ValueError:
		bot.send_message(chat_id=msg_data.chat.id, text="Wrong channel id.")
		return

	if msg_data.text.startswith("/add_main_channel"):
		if db_utils.is_main_channel_exists(channel_id):
			bot.send_message(chat_id=msg_data.chat.id, text="This channel already added.")
			return
		db_utils.insert_main_channel(channel_id)
		bot.send_message(chat_id=msg_data.chat.id, text="Main channel was successfully added.")
	elif msg_data.text.startswith("/remove_main_channel"):
		if not db_utils.is_main_channel_exists(channel_id):
			bot.send_message(chat_id=msg_data.chat.id, text="Wrong main channel id.")
			return
		db_utils.delete_main_channel(channel_id)
		bot.send_message(chat_id=msg_data.chat.id, text="Main channel was successfully removed.")

	config_utils.load_discussion_chat_ids(bot)


def handle_user_change(bot: telebot.TeleBot, msg_data: telebot.types.Message, arguments: str):
	if msg_data.text.startswith("/set_user_tag"):
		try:
			main_channel_id, tag, user = arguments.split(" ")
		except ValueError:
			bot.send_message(chat_id=msg_data.chat.id, text="Wrong arguments.")
			return

		if not db_utils.is_main_channel_exists(main_channel_id):
			bot.send_message(chat_id=msg_data.chat.id, text="Wrong main channel id.")
			return

		found_user = core_api.get_user(user)
		# use core api to get user id because telegram bot api can't get user by username
		if found_user:
			found_user = user_utils.get_user(bot, found_user.id)
		else:
			found_user = user_utils.get_user(bot, user)

		if not found_user:
			if user.startswith("@"):
				bot.send_message(chat_id=msg_data.chat.id, text="Can't find user by provided username.")
			else:
				bot.send_message(chat_id=msg_data.chat.id, text="Can't find user by provided id.")
			return

		user = found_user.id

		is_tag_already_exists = db_utils.is_user_tag_exists(main_channel_id, tag)

		db_utils.insert_or_update_user(main_channel_id, tag, user)
		user_utils.load_users(bot)

		if not is_tag_already_exists:
			channel_manager.add_new_user_tag_to_channels(main_channel_id, tag)

		if main_channel_id in config_utils.DISCUSSION_CHAT_DATA:
			discussion_channel_id = config_utils.DISCUSSION_CHAT_DATA.get(main_channel_id)
			if discussion_channel_id:
				if is_tag_already_exists:
					comment_text = f"User tag #{tag} was reassigned to {{USER}}."
					text, entities = user_utils.insert_user_reference(main_channel_id, tag, comment_text)
					bot.send_message(chat_id=discussion_channel_id, text=text, entities=entities)
				else:
					comment_text = f"User tag #{tag} was added, assigned user is {{USER}}."
					text, entities = user_utils.insert_user_reference(main_channel_id, tag, comment_text)
					bot.send_message(chat_id=discussion_channel_id, text=text, entities=entities)

		bot.send_message(chat_id=msg_data.chat.id, text="User tag was successfully updated.")
	elif msg_data.text.startswith("/remove_user_tag"):
		try:
			main_channel_id, tag = arguments.split(" ")
		except ValueError:
			bot.send_message(chat_id=msg_data.chat.id, text="Wrong arguments.")
			return

		if not db_utils.is_main_channel_exists(main_channel_id):
			bot.send_message(chat_id=msg_data.chat.id, text="Wrong main channel id.")
			return

		if not db_utils.is_user_tag_exists(main_channel_id, tag):
			bot.send_message(chat_id=msg_data.chat.id, text="This user tag doesn't exists.")
			return

		db_utils.delete_user_by_tag(main_channel_id, tag)
		channel_manager.remove_user_tag_from_channels(main_channel_id, tag)
		user_utils.load_users(bot)

		if main_channel_id in config_utils.DISCUSSION_CHAT_DATA:
			discussion_channel_id = config_utils.DISCUSSION_CHAT_DATA.get(main_channel_id)
			if discussion_channel_id:
				comment_text = f"User tag #{tag} was deleted."
				bot.send_message(chat_id=discussion_channel_id, text=comment_text)

		bot.send_message(chat_id=msg_data.chat.id, text="User tag was removed.")


def handle_set_default_subchannel(bot: telebot.TeleBot, msg_data: telebot.types.Message, arguments: str):
	try:
		main_channel_id, tag, priority = arguments.split(" ")
	except ValueError:
		bot.send_message(chat_id=msg_data.chat.id, text="Wrong arguments.")
		return

	if not db_utils.is_main_channel_exists(main_channel_id):
		bot.send_message(chat_id=msg_data.chat.id, text="Wrong main channel id.")
		return

	config_utils.DEFAULT_USER_DATA[main_channel_id] = f"{tag} {priority}"

	bot.send_message(chat_id=msg_data.chat.id, text="Default subchannel successfully changed.")
	config_utils.update_config({"DEFAULT_USER_DATA": config_utils.DEFAULT_USER_DATA})


def handle_change_auto_forwarding(bot: telebot.TeleBot, msg_data: telebot.types.Message, arguments: str):
	if msg_data.text.startswith("/enable"):
		config_utils.AUTO_FORWARDING_ENABLED = True
	elif msg_data.text.startswith("/disable"):
		config_utils.AUTO_FORWARDING_ENABLED = False
	state = "enabled" if config_utils.AUTO_FORWARDING_ENABLED else "disabled"
	bot.send_message(chat_id=msg_data.chat.id, text=f"Auto forwarding now is {state}.")
	config_utils.update_config({"AUTO_FORWARDING_ENABLED": config_utils.AUTO_FORWARDING_ENABLED})


def handle_change_button_text(bot: telebot.TeleBot, msg_data: telebot.types.Message, arguments: str):
	space_index = arguments.find(" ")
	button_name = arguments[:space_index]
	arguments = arguments[space_index + 1:]

	if button_name == "opened":
		config_utils.BUTTON_TEXTS["OPENED_TICKET"] = arguments
	elif button_name == "closed":
		config_utils.BUTTON_TEXTS["CLOSED_TICKET"] = arguments
	elif button_name == "assigned":
		config_utils.BUTTON_TEXTS["ASSIGNED_USER_PREFIX"] = arguments
	elif button_name == "cc":
		config_utils.BUTTON_TEXTS["CC"] = arguments
	elif button_name == "schedule":
		config_utils.BUTTON_TEXTS["SCHEDULE_MESSAGE"] = arguments
	elif button_name == "check":
		config_utils.BUTTON_TEXTS["CHECK"] = arguments
	elif button_name == "priority":
		no_priority, first_priority, second_priority, third_priority = arguments.split(" ")
		config_utils.BUTTON_TEXTS["PRIORITIES"] = {
			"-": no_priority,
			"1": first_priority,
			"2": second_priority,
			"3": third_priority
		}
	else:
		bot.send_message(chat_id=msg_data.chat.id, text=f"Unknown button name.")
		return
	bot.send_message(chat_id=msg_data.chat.id, text=f"Successfully updated button text.")
	interval_updating_utils.start_interval_updating(bot)
	config_utils.update_config({"BUTTON_TEXTS": config_utils.BUTTON_TEXTS})


def handle_change_hashtag_text(bot: telebot.TeleBot, msg_data: telebot.types.Message, arguments: str):
	try:
		tag_name, new_value = arguments.split(" ")
	except ValueError:
		bot.send_message(chat_id=msg_data.chat.id, text="Wrong arguments.")
		return

	if config_utils.HASHTAGS_BEFORE_UPDATE is None:
		config_utils.HASHTAGS_BEFORE_UPDATE = copy.deepcopy(config_utils.HASHTAGS)

	if tag_name == "opened":
		if hashtag_data.OPENED_TAG != config_utils.HASHTAGS_BEFORE_UPDATE["OPENED"]:
			bot.send_message(chat_id=msg_data.chat.id, text=f"Wait until previous update is finished.")
			return
		config_utils.HASHTAGS["OPENED"] = new_value
		hashtag_data.OPENED_TAG = new_value
	elif tag_name == "closed":
		if hashtag_data.CLOSED_TAG != config_utils.HASHTAGS_BEFORE_UPDATE["CLOSED"]:
			bot.send_message(chat_id=msg_data.chat.id, text=f"Wait until previous update is finished.")
			return
		config_utils.HASHTAGS["CLOSED"] = new_value
		hashtag_data.CLOSED_TAG = new_value
	elif tag_name == "scheduled":
		if hashtag_data.SCHEDULED_TAG != config_utils.HASHTAGS_BEFORE_UPDATE["SCHEDULED"]:
			bot.send_message(chat_id=msg_data.chat.id, text=f"Wait until previous update is finished.")
			return
		config_utils.HASHTAGS["SCHEDULED"] = new_value
		hashtag_data.SCHEDULED_TAG = new_value
	elif tag_name == "priority":
		if hashtag_data.PRIORITY_TAG != config_utils.HASHTAGS_BEFORE_UPDATE["PRIORITY"]:
			bot.send_message(chat_id=msg_data.chat.id, text=f"Wait until previous update is finished.")
			return
		config_utils.HASHTAGS["PRIORITY"] = new_value
		hashtag_data.PRIORITY_TAG = new_value
	else:
		if config_utils.HASHTAGS_BEFORE_UPDATE == config_utils.HASHTAGS:
			config_utils.HASHTAGS_BEFORE_UPDATE = None
		bot.send_message(chat_id=msg_data.chat.id, text=f"Unknown hashtag name.")
		return

	bot.send_message(chat_id=msg_data.chat.id, text=f"Successfully changed hashtag text.")
	interval_updating_utils.start_interval_updating(bot)
	config_utils.update_config({"HASHTAGS": config_utils.HASHTAGS})
	config_utils.update_config({"HASHTAGS_BEFORE_UPDATE": config_utils.HASHTAGS_BEFORE_UPDATE})


def handle_change_remind_without_interaction(bot: telebot.TeleBot, msg_data: telebot.types.Message, arguments: str):
	try:
		new_time = int(arguments)
	except ValueError:
		bot.send_message(chat_id=msg_data.chat.id, text="You need to specify a number.")
		return
	config_utils.REMINDER_TIME_WITHOUT_INTERACTION = new_time
	bot.send_message(chat_id=msg_data.chat.id, text="Reminder time without interaction successfully changed.")
	config_utils.update_config({"REMINDER_TIME_WITHOUT_INTERACTION": config_utils.REMINDER_TIME_WITHOUT_INTERACTION})


COMMAND_LIST = [
	["/help", "Command explanations", handle_help_command],
	["/set_dump_chat_id", "Set dump chat id", handle_set_dump_chat_id],
	["/set_interval_check_time", "Set time between interval checks", handle_set_interval_check],
	["/set_timezone", "Set timezone", handle_set_timezone],
	["/add_main_channel", "Add main channel", handle_main_channel_change],
	["/remove_main_channel", "Remove main channel", handle_main_channel_change],
	["/set_user_tag", "Add user id", handle_user_change],
	["/remove_user_tag", "Remove user id", handle_user_change],
	["/set_default_subchannel", "Set default subchannel", handle_set_default_subchannel],
	["/enable_auto_forwarding", "Enables auto forwarding during scanning", handle_change_auto_forwarding],
	["/disable_auto_forwarding", "Enables auto forwarding during scanning", handle_change_auto_forwarding],
	["/set_button_text", "Set text of specified button", handle_change_button_text],
	["/set_hashtag_text", "Set text of specified hashtag", handle_change_hashtag_text],
	["/set_remind_without_interaction", "Set time for reminding users", handle_change_remind_without_interaction],
]

