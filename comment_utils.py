import telebot
from telebot.apihelper import ApiTelegramException

import daily_reminder
import db_utils
import interval_updating_utils
import utils
import forwarding_utils
from config_utils import DISCUSSION_CHAT_DATA
from hashtag_data import HashtagData

_NEXT_ACTION_COMMENT_PREFIX = ":"
_NEXT_ACTION_TEXT_PREFIX = "::"


def save_comment(bot: telebot.TeleBot, msg_data: telebot.types.Message):
	discussion_message_id = msg_data.message_id
	discussion_chat_id = msg_data.chat.id

	reply_to_message_id = msg_data.reply_to_message.message_id

	sender_id = msg_data.from_user.id
	db_utils.insert_comment_message(reply_to_message_id, discussion_message_id, discussion_chat_id, sender_id)

	main_channel_id = utils.get_key_by_value(DISCUSSION_CHAT_DATA, discussion_chat_id)
	if main_channel_id is None:
		return

	main_channel_id = int(main_channel_id)
	top_discussion_message_id = db_utils.get_comment_top_parent(discussion_message_id, discussion_chat_id)
	if top_discussion_message_id == discussion_message_id:
		return
	main_message_id = db_utils.get_main_from_discussion_message(top_discussion_message_id, main_channel_id)

	if main_message_id:
		if msg_data.text.startswith(_NEXT_ACTION_COMMENT_PREFIX):
			next_action_text = msg_data.text[len(_NEXT_ACTION_COMMENT_PREFIX):]
			update_next_action(bot, main_message_id, main_channel_id, next_action_text)
		interval_updating_utils.update_older_message(bot, main_channel_id, main_message_id)

		daily_reminder.update_user_last_interaction(main_message_id, main_channel_id, msg_data)
		daily_reminder.set_ticket_update_time(main_message_id, main_channel_id)


def update_next_action(bot: telebot.TeleBot, main_message_id: int, main_channel_id: int, next_action: str):
	try:
		post_data = utils.get_main_message_content_by_id(bot, main_channel_id, main_message_id)
	except ApiTelegramException:
		utils.delete_main_message(bot, main_channel_id, main_message_id)
		return

	text, entities = utils.get_post_content(post_data)
	if _NEXT_ACTION_TEXT_PREFIX in text:
		next_action_prefix_index = text.find(_NEXT_ACTION_TEXT_PREFIX)
		text = text[:next_action_prefix_index]

	next_action_with_prefix = _NEXT_ACTION_TEXT_PREFIX + next_action
	text += next_action_with_prefix
	utils.set_post_content(post_data, text, entities)

	hashtag_data = HashtagData(post_data, main_channel_id)
	keyboard_markup = forwarding_utils.generate_control_buttons(hashtag_data, post_data)

	utils.edit_message_content(bot, post_data, chat_id=main_channel_id,
	                           message_id=main_message_id, reply_markup=keyboard_markup)

	# for compatibility with older versions
	db_utils.insert_or_update_current_next_action(main_message_id, main_channel_id, next_action)
	db_utils.update_previous_next_action(main_message_id, main_channel_id, next_action_with_prefix)
