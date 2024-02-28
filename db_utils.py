import logging
import sqlite3
import threading

DB_FILENAME = "taskhelper_data.db"

DB_CONNECTION = sqlite3.connect(DB_FILENAME, check_same_thread=False)
CURSOR = DB_CONNECTION.cursor()

_DB_LOCK = threading.RLock()


def db_thread_lock(func):
	def inner_function(*args, **kwargs):
		with _DB_LOCK:
			try:
				return func(*args, **kwargs)
			except sqlite3.Error as E:
				logging.error(f"SQLite error in {func.__name__} function, error: {E.args}")
	return inner_function


def initialize_db():
	create_tables()


def is_table_exists(table_name):
	sql = "SELECT count(name) FROM sqlite_master WHERE type='table' AND name=(?)"
	CURSOR.execute(sql, (table_name,))
	result = CURSOR.fetchone()[0]
	return bool(result)


def create_tables():
	if not is_table_exists("discussion_messages"):
		discussion_messages_table_sql = '''
			CREATE TABLE "discussion_messages" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"main_message_id"	INT NOT NULL,
				"main_channel_id"	INT NOT NULL,
				"discussion_message_id"	INT NOT NULL
			); '''

		CURSOR.execute(discussion_messages_table_sql)

	if not is_table_exists("copied_messages"):
		copied_messages_table_sql = '''
			CREATE TABLE "copied_messages" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"main_message_id"	INT NOT NULL,
				"main_channel_id"	INT NOT NULL,
				"copied_message_id"	INT NOT NULL,
				"copied_channel_id"	INT NOT NULL
			); '''

		CURSOR.execute(copied_messages_table_sql)

	if not is_table_exists("last_message_ids"):
		last_message_ids_table_sql = '''
			CREATE TABLE "last_message_ids" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"chat_id"	INT NOT NULL,
				"last_message_id"	INT NOT NULL
			); '''

		CURSOR.execute(last_message_ids_table_sql)

	if not is_table_exists("comment_messages"):
		comment_messages_table_sql = '''
			CREATE TABLE "comment_messages" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"discussion_chat_id"	INT NOT NULL,
				"message_id"	INT NOT NULL,
				"reply_to_message_id"	INT NOT NULL,
				"sender_id"	INT NOT NULL
			); '''

		CURSOR.execute(comment_messages_table_sql)

	if not is_table_exists("scheduled_messages"):
		scheduled_messages_table_sql = '''
			CREATE TABLE "scheduled_messages" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"main_message_id"	INT NOT NULL,
				"main_channel_id"	INT NOT NULL,
				"scheduled_message_id"	INT NOT NULL,
				"scheduled_channel_id"	INT NOT NULL,
				"send_time"	INT NOT NULL
			); '''

		CURSOR.execute(scheduled_messages_table_sql)

	if not is_table_exists("interval_updates_status"):
		interval_updates_status_table_sql = '''
			CREATE TABLE "interval_updates_status" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"main_channel_id"	INT NOT NULL,
				"current_message_id"    INT NOT NULL
			); '''

		CURSOR.execute(interval_updates_status_table_sql)

	if not is_table_exists("individual_channel_settings"):
		individual_channel_settings_table_sql = '''
			CREATE TABLE "individual_channel_settings" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"main_channel_id"	INT NOT NULL,
				"channel_id"        INT NOT NULL,
				"priorities"        TEXT,
				"settings"          TEXT,
				"user_id"           INT
			); '''

		CURSOR.execute(individual_channel_settings_table_sql)

	if not is_table_exists("users"):
		users_table_sql = '''
			CREATE TABLE "users" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"main_channel_id"	INT NOT NULL,
				"user_id"           INT NOT NULL,
				"user_tag"          TEXT NOT NULL		
			); '''

		CURSOR.execute(users_table_sql)

	if not is_table_exists("main_channels"):
		main_channels_table_sql = '''
			CREATE TABLE "main_channels" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"channel_id"    INT NOT NULL
			); '''

		CURSOR.execute(main_channels_table_sql)

	if not is_table_exists("main_messages"):
		main_messages_table_sql = '''
			CREATE TABLE "main_messages" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"main_channel_id"   INT NOT NULL,
				"main_message_id"   INT NOT NULL,
				"sender_id"         INT
			); '''

		CURSOR.execute(main_messages_table_sql)

	if not is_table_exists("next_action_comments"):
		next_action_comments_table_sql = '''
			CREATE TABLE "next_action_comments" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"main_channel_id"       INT NOT NULL,
				"main_message_id"       INT NOT NULL,
				"previous_comment_text" TEXT,
				"current_comment_text"  TEXT
			); '''

		CURSOR.execute(next_action_comments_table_sql)

	if not is_table_exists("tickets_data"):
		tickets_data_table_sql = '''
			CREATE TABLE "tickets_data" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"main_channel_id"       INT NOT NULL,
				"main_message_id"       INT NOT NULL,
				"is_opened"             int,
				"user_tags"             TEXT,
				"priority"              TEXT,
				"update_time"           INT
			); '''

		CURSOR.execute(tickets_data_table_sql)

	if not is_table_exists("user_reminder_data"):
		user_interactions_table_sql = '''
			CREATE TABLE "user_reminder_data" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"main_channel_id"           INT NOT NULL,
				"user_tag"                  TEXT NOT NULL,
				"last_interaction_time"     INT
			); '''

		CURSOR.execute(user_interactions_table_sql)

	if not is_table_exists("reminded_tickets"):
		reminded_tickets_table_sql = '''
			CREATE TABLE "reminded_tickets" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"main_channel_id"           INT NOT NULL,
				"main_message_id"           INT NOT NULL,
				"user_tag"                  TEXT NOT NULL,
				"reminded_at"               INT NOT NULL
			); '''

		CURSOR.execute(reminded_tickets_table_sql)

	if not is_table_exists("custom_channel_hashtags"):
		custom_channel_hashtags_table_sql = '''
			CREATE TABLE "custom_channel_hashtags" (
				"id"	INTEGER PRIMARY KEY AUTOINCREMENT,
				"channel_id"           INT NOT NULL,
				"custom_hashtag"       TEXT
			); '''

		CURSOR.execute(custom_channel_hashtags_table_sql)

	DB_CONNECTION.commit()


@db_thread_lock
def insert_or_update_discussion_message(main_message_id, main_channel_id, discussion_message_id):
	if get_discussion_message_id(main_message_id, main_channel_id):
		sql = "UPDATE discussion_messages SET discussion_message_id=(?) WHERE main_message_id=(?) and main_channel_id=(?)"
	else:
		sql = "INSERT INTO discussion_messages (discussion_message_id, main_message_id, main_channel_id) VALUES (?, ?, ?)"

	CURSOR.execute(sql, (discussion_message_id, main_message_id, main_channel_id, ))
	DB_CONNECTION.commit()


@db_thread_lock
def get_discussion_message_id(main_message_id, main_channel_id):
	sql = "SELECT discussion_message_id FROM discussion_messages WHERE main_message_id=(?) and main_channel_id=(?)"
	CURSOR.execute(sql, (main_message_id, main_channel_id,))
	result = CURSOR.fetchone()
	if result:
		return result[0]


@db_thread_lock
def get_main_from_discussion_message(discussion_message_id, main_channel_id):
	sql = "SELECT main_message_id FROM discussion_messages WHERE discussion_message_id=(?) and main_channel_id=(?)"
	CURSOR.execute(sql, (discussion_message_id, main_channel_id,))
	result = CURSOR.fetchone()
	if result:
		return result[0]


@db_thread_lock
def insert_copied_message(main_message_id, main_channel_id, copied_message_id, copied_channel_id):
	sql = "INSERT INTO copied_messages (copied_message_id, copied_channel_id, main_message_id, main_channel_id) VALUES (?, ?, ?, ?)"
	CURSOR.execute(sql, (copied_message_id, copied_channel_id, main_message_id, main_channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def delete_copied_message(copied_message_id, copied_channel_id):
	sql = "DELETE FROM copied_messages WHERE copied_message_id=(?) and copied_channel_id=(?)"
	CURSOR.execute(sql, (copied_message_id, copied_channel_id))
	DB_CONNECTION.commit()


@db_thread_lock
def get_copied_message_data(main_message_id, main_channel_id):
	sql = "SELECT copied_message_id, copied_channel_id FROM copied_messages WHERE main_message_id=(?) and main_channel_id=(?)"
	CURSOR.execute(sql, (main_message_id, main_channel_id,))
	result = CURSOR.fetchall()
	return result


@db_thread_lock
def get_main_message_from_copied(copied_message_id, copied_channel_id):
	sql = "SELECT main_message_id, main_channel_id FROM copied_messages WHERE copied_message_id=(?) and copied_channel_id=(?)"
	CURSOR.execute(sql, (copied_message_id, copied_channel_id,))
	result = CURSOR.fetchone()
	if result:
		return result


@db_thread_lock
def get_oldest_copied_message(copied_channel_id):
	sql = "SELECT min(copied_message_id) FROM copied_messages WHERE copied_channel_id=(?)"
	CURSOR.execute(sql, (copied_channel_id,))
	result = CURSOR.fetchone()
	if result:
		return result[0]


@db_thread_lock
def update_copied_message_id(copied_message_id, copied_channel_id, updated_message_id):
	sql = "UPDATE copied_messages SET copied_message_id=(?) WHERE copied_message_id=(?) AND copied_channel_id=(?)"
	CURSOR.execute(sql, (updated_message_id, copied_message_id, copied_channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def get_copied_messages_from_main(main_message_id, main_channel_id):
	sql = "SELECT copied_message_id, copied_channel_id FROM copied_messages WHERE main_message_id=(?) AND main_channel_id=(?)"
	CURSOR.execute(sql, (main_message_id, main_channel_id,))
	result = CURSOR.fetchall()
	return result


@db_thread_lock
def insert_or_update_last_msg_id(last_message_id, chat_id):
	if get_last_message_id(chat_id):
		sql = "UPDATE last_message_ids SET last_message_id=(?) WHERE chat_id=(?)"
	else:
		sql = "INSERT INTO last_message_ids (last_message_id, chat_id) VALUES (?, ?)"

	CURSOR.execute(sql, (last_message_id, chat_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def get_last_message_id(chat_id):
	sql = "SELECT last_message_id FROM last_message_ids WHERE chat_id=(?)"
	CURSOR.execute(sql, (chat_id,))
	result = CURSOR.fetchone()
	if result:
		return result[0]


@db_thread_lock
def insert_comment_message(reply_to_message_id, discussion_message_id, discussion_chat_id, sender_id):
	if is_comment_exist(discussion_message_id, discussion_chat_id):
		return

	sql = "INSERT INTO comment_messages (reply_to_message_id, message_id, discussion_chat_id, sender_id) VALUES (?, ?, ?, ?)"
	CURSOR.execute(sql, (reply_to_message_id, discussion_message_id, discussion_chat_id, sender_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def is_comment_exist(discussion_message_id, discussion_chat_id):
	sql = "SELECT id FROM comment_messages WHERE message_id=(?) and discussion_chat_id=(?)"
	CURSOR.execute(sql, (discussion_message_id, discussion_chat_id,))
	result = CURSOR.fetchone()
	return bool(result)


@db_thread_lock
def get_comments_count(discussion_message_id, discussion_chat_id, ignored_sender_id=0):
	sql = '''
		WITH RECURSIVE
		  reply_messages(comment_id) AS (
			 SELECT (?)
			 UNION ALL
			 SELECT message_id FROM comment_messages, reply_messages WHERE reply_to_message_id = reply_messages.comment_id
			 AND discussion_chat_id = (?) AND sender_id != (?)
		  )
		SELECT count(comment_id) - 1 FROM reply_messages;
	'''

	CURSOR.execute(sql, (discussion_message_id, discussion_chat_id, ignored_sender_id,))
	result = CURSOR.fetchone()
	return result[0]


@db_thread_lock
def get_comment_top_parent(discussion_message_id, discussion_chat_id):
	sql = '''
		WITH RECURSIVE
		  reply_messages(comment_id) AS (
		   SELECT (?)
		   UNION ALL
		   SELECT reply_to_message_id FROM comment_messages, reply_messages WHERE message_id = reply_messages.comment_id
		   AND discussion_chat_id = (?)
		  )
		SELECT MIN(comment_id) FROM reply_messages;	
	'''

	CURSOR.execute(sql, (discussion_message_id, discussion_chat_id,))
	result = CURSOR.fetchone()
	return result[0]


@db_thread_lock
def get_last_comment(discussion_message_id, discussion_chat_id, ignored_sender_id=0):
	sql = '''
		WITH RECURSIVE
		  reply_messages(comment_id) AS (
			 SELECT (?)
			 UNION ALL
			 SELECT message_id FROM comment_messages, reply_messages WHERE reply_to_message_id = reply_messages.comment_id
			 AND discussion_chat_id = (?) AND sender_id != (?)
		  )
		SELECT MAX(comment_id) FROM reply_messages;
	'''

	CURSOR.execute(sql, (discussion_message_id, discussion_chat_id, ignored_sender_id,))
	result = CURSOR.fetchone()
	return result[0]


@db_thread_lock
def insert_scheduled_message(main_message_id, main_channel_id, scheduled_message_id, scheduled_channel_id, send_time):
	sql = "INSERT INTO scheduled_messages (main_message_id, main_channel_id, scheduled_message_id, scheduled_channel_id, send_time) VALUES (?, ?, ?, ?, ?)"
	CURSOR.execute(sql, (main_message_id, main_channel_id, scheduled_message_id, scheduled_channel_id, send_time,))
	DB_CONNECTION.commit()


@db_thread_lock
def update_scheduled_message(main_message_id, main_channel_id, send_time):
	sql = "UPDATE scheduled_messages SET send_time=(?) WHERE main_message_id=(?) and main_channel_id=(?)"
	CURSOR.execute(sql, (send_time, main_message_id, main_channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def get_scheduled_message_send_time(main_message_id, main_channel_id):
	sql = "SELECT send_time FROM scheduled_messages WHERE main_message_id=(?) and main_channel_id=(?)"
	CURSOR.execute(sql, (main_message_id, main_channel_id,))
	result = CURSOR.fetchone()
	if result:
		return result[0]


@db_thread_lock
def is_message_scheduled(main_message_id, main_channel_id):
	sql = "SELECT id FROM scheduled_messages WHERE main_message_id=(?) and main_channel_id=(?)"
	CURSOR.execute(sql, (main_message_id, main_channel_id,))
	result = CURSOR.fetchone()
	return bool(result)


@db_thread_lock
def delete_scheduled_message_main(main_message_id, main_channel_id):
	sql = "DELETE FROM scheduled_messages WHERE main_message_id=(?) AND main_channel_id=(?)"
	CURSOR.execute(sql, (main_message_id, main_channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def get_all_scheduled_messages():
	sql = "SELECT main_message_id, main_channel_id, send_time FROM scheduled_messages"
	CURSOR.execute(sql, ())
	result = CURSOR.fetchall()
	return result


@db_thread_lock
def get_finished_update_channels():
	sql = "SELECT main_channel_id FROM interval_updates_status WHERE current_message_id <= 0"
	CURSOR.execute(sql, ())
	result = CURSOR.fetchall()
	return result


@db_thread_lock
def get_unfinished_update_channel():
	sql = "SELECT main_channel_id, current_message_id FROM interval_updates_status WHERE current_message_id > 0"
	CURSOR.execute(sql, ())
	result = CURSOR.fetchone()
	if result:
		return result


@db_thread_lock
def insert_or_update_channel_update_progress(main_channel_id, current_message_id):
	if get_update_in_progress_channel(main_channel_id):
		sql = "UPDATE interval_updates_status SET current_message_id=(?) WHERE main_channel_id=(?)"
	else:
		sql = "INSERT INTO interval_updates_status(current_message_id, main_channel_id) VALUES (?, ?)"
	CURSOR.execute(sql, (current_message_id, main_channel_id))
	DB_CONNECTION.commit()


@db_thread_lock
def get_update_in_progress_channel(main_channel_id):
	sql = "SELECT current_message_id FROM interval_updates_status WHERE main_channel_id=(?)"
	CURSOR.execute(sql, (main_channel_id,))
	result = CURSOR.fetchone()
	if result:
		return result


@db_thread_lock
def clear_updates_in_progress():
	sql = "DELETE FROM interval_updates_status"
	CURSOR.execute(sql, ())
	DB_CONNECTION.commit()


@db_thread_lock
def get_main_channel_ids():
	sql = "SELECT channel_id FROM main_channels"
	CURSOR.execute(sql, ())
	result = CURSOR.fetchall()
	if result:
		return [row[0] for row in result]
	else:
		return []


@db_thread_lock
def is_main_channel_exists(main_channel_id):
	sql = "SELECT id FROM main_channels WHERE channel_id=(?)"
	CURSOR.execute(sql, (main_channel_id,))
	result = CURSOR.fetchone()
	return bool(result)


@db_thread_lock
def insert_main_channel(main_channel_id):
	sql = "INSERT INTO main_channels(channel_id) VALUES (?)"
	CURSOR.execute(sql, (main_channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def delete_main_channel(main_channel_id):
	sql = "DELETE FROM main_channels WHERE channel_id=(?)"
	CURSOR.execute(sql, (main_channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def get_main_channel_from_user(user_id):
	sql = "SELECT main_channel_id FROM users WHERE user_id=(?)"
	CURSOR.execute(sql, (user_id,))
	result = CURSOR.fetchone()
	if result:
		return result[0]


@db_thread_lock
def get_tags_from_user_id(user_id):
	sql = "SELECT user_tag FROM users WHERE user_id=(?)"
	CURSOR.execute(sql, (user_id,))
	result = CURSOR.fetchall()  # one user can have multiple tags assigned to him
	if result:
		return [row[0] for row in result]
	else:
		return []


@db_thread_lock
def get_main_channel_user_tags(main_channel_id):
	sql = "SELECT user_tag FROM users WHERE main_channel_id=(?)"
	CURSOR.execute(sql, (main_channel_id,))
	result = CURSOR.fetchall()
	if result:
		return [row[0] for row in result]


@db_thread_lock
def insert_or_update_user(main_channel_id, user_tag, user_id):
	if is_user_tag_exists(main_channel_id, user_tag):
		sql = "UPDATE users SET user_id=(?) WHERE main_channel_id=(?) AND user_tag=(?)"
	else:
		sql = "INSERT INTO users(user_id, main_channel_id, user_tag) VALUES (?, ?, ?)"

	CURSOR.execute(sql, (user_id, main_channel_id, user_tag,))
	DB_CONNECTION.commit()


@db_thread_lock
def delete_user_by_tag(main_channel_id, user_tag):
	sql = "DELETE FROM users WHERE main_channel_id=(?) AND user_tag=(?)"
	CURSOR.execute(sql, (main_channel_id, user_tag,))
	DB_CONNECTION.commit()


@db_thread_lock
def get_main_message_sender(main_channel_id, main_message_id):
	sql = "SELECT sender_id FROM main_messages WHERE main_channel_id=(?) AND main_message_id=(?)"
	CURSOR.execute(sql, (main_channel_id, main_message_id,))
	result = CURSOR.fetchone()
	if result:
		return result[0]


@db_thread_lock
def insert_main_channel_message(main_channel_id, main_message_id, sender_id):
	if not is_main_message_exists(main_channel_id, main_message_id):
		sql = '''
			INSERT INTO main_messages
			(main_channel_id, main_message_id, sender_id)
			VALUES (?, ?, ?)
		'''
		CURSOR.execute(sql, (main_channel_id, main_message_id, sender_id,))
		DB_CONNECTION.commit()


@db_thread_lock
def delete_main_channel_message(main_channel_id, main_message_id):
	sql = "DELETE FROM main_messages WHERE main_channel_id = (?) AND main_message_id = (?)"
	CURSOR.execute(sql, (main_channel_id, main_message_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def is_main_message_exists(main_channel_id, main_message_id):
	sql = "SELECT id FROM main_messages WHERE main_channel_id=(?) AND main_message_id=(?)"
	CURSOR.execute(sql, (main_channel_id, main_message_id,))
	result = CURSOR.fetchone()
	return bool(result)


@db_thread_lock
def is_user_tag_exists(main_channel_id, user_tag):
	sql = "SELECT id FROM users WHERE main_channel_id=(?) AND user_tag=(?)"
	CURSOR.execute(sql, (main_channel_id, user_tag,))
	result = CURSOR.fetchone()
	return bool(result)


@db_thread_lock
def get_all_users():
	sql = "SELECT main_channel_id, user_id, user_tag FROM users"
	CURSOR.execute(sql, ())
	result = CURSOR.fetchall()
	return result


@db_thread_lock
def get_next_action_text(main_message_id, main_channel_id):
	sql = "SELECT previous_comment_text, current_comment_text FROM next_action_comments WHERE main_channel_id=(?) AND main_message_id=(?)"
	CURSOR.execute(sql, (main_channel_id, main_message_id,))
	result = CURSOR.fetchone()
	return result


@db_thread_lock
def insert_or_update_current_next_action(main_message_id, main_channel_id, comment_text):
	if get_next_action_text(main_message_id, main_channel_id):
		sql = "UPDATE next_action_comments SET current_comment_text=(?) WHERE main_message_id=(?) and main_channel_id=(?)"
	else:
		sql = "INSERT INTO next_action_comments (current_comment_text, main_message_id, main_channel_id) VALUES (?, ?, ?)"

	CURSOR.execute(sql, (comment_text, main_message_id, main_channel_id, ))
	DB_CONNECTION.commit()


@db_thread_lock
def update_previous_next_action(main_message_id, main_channel_id, comment_text):
	sql = "UPDATE next_action_comments SET previous_comment_text=(?) WHERE main_message_id=(?) and main_channel_id=(?)"
	CURSOR.execute(sql, (comment_text, main_message_id, main_channel_id, ))
	DB_CONNECTION.commit()


@db_thread_lock
def insert_or_update_ticket_data(main_message_id, main_channel_id, is_opened, user_tags, priority):
	if get_ticket_data(main_message_id, main_channel_id):
		sql = "UPDATE tickets_data SET is_opened=(?), user_tags=(?), priority=(?) WHERE main_message_id=(?) and main_channel_id=(?)"
	else:
		sql = "INSERT INTO tickets_data(is_opened, user_tags, priority, main_message_id, main_channel_id) VALUES (?, ?, ?, ?, ?)"
	is_opened = 1 if is_opened else 0
	CURSOR.execute(sql, (is_opened, user_tags, priority, main_message_id, main_channel_id, ))
	DB_CONNECTION.commit()


@db_thread_lock
def get_ticket_data(main_message_id, main_channel_id):
	sql = "SELECT user_tags, priority, update_time FROM tickets_data WHERE main_message_id=(?) and main_channel_id=(?)"
	CURSOR.execute(sql, (main_message_id, main_channel_id, ))
	result = CURSOR.fetchone()
	return result


@db_thread_lock
def set_ticket_update_time(main_message_id, main_channel_id, update_time):
	sql = "UPDATE tickets_data SET update_time=(?) WHERE main_message_id=(?) AND main_channel_id=(?)"
	CURSOR.execute(sql, (update_time, main_message_id, main_channel_id, ))
	DB_CONNECTION.commit()


@db_thread_lock
def get_user_highest_priority(main_channel_id, user_tag):
	sql = "SELECT min(priority) FROM tickets_data WHERE user_tags LIKE '%' || ? || '%' AND main_channel_id=(?)"
	CURSOR.execute(sql, (user_tag, main_channel_id,))
	result = CURSOR.fetchone()
	return result[0]


@db_thread_lock
def delete_ticket_data(main_message_id, main_channel_id):
	sql = "DELETE FROM tickets_data WHERE main_message_id=(?) AND main_channel_id=(?)"
	CURSOR.execute(sql, (main_message_id, main_channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def insert_or_update_last_user_interaction(main_channel_id, user_tag, interaction_time):
	if is_user_reminder_data_exists(main_channel_id, user_tag):
		sql = "UPDATE user_reminder_data SET last_interaction_time=(?) WHERE user_tag=(?) AND main_channel_id=(?)"
	else:
		sql = "INSERT INTO user_reminder_data(last_interaction_time, user_tag, main_channel_id) VALUES (?, ?, ?)"
	CURSOR.execute(sql, (interaction_time, user_tag, main_channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def get_last_interaction_time(main_channel_id, user_tag):
	sql = "SELECT last_interaction_time FROM user_reminder_data WHERE user_tag=(?) AND main_channel_id=(?)"
	CURSOR.execute(sql, (user_tag, main_channel_id,))
	result = CURSOR.fetchone()
	if result:
		return result[0]


@db_thread_lock
def is_user_reminder_data_exists(main_channel_id, user_tag):
	sql = "SELECT id FROM user_reminder_data WHERE user_tag=(?) AND main_channel_id=(?)"
	CURSOR.execute(sql, (user_tag, main_channel_id,))
	result = CURSOR.fetchone()
	return bool(result)


@db_thread_lock
def get_ticket_remind_time(main_message_id, main_channel_id, user_tag):
	sql = "SELECT reminded_at FROM reminded_tickets WHERE main_message_id=(?) AND main_channel_id=(?) AND user_tag=(?)"
	CURSOR.execute(sql, (main_message_id, main_channel_id, user_tag,))
	result = CURSOR.fetchone()
	if result:
		return result[0]


@db_thread_lock
def insert_or_update_remind_time(main_message_id, main_channel_id, user_tag, remind_time):
	if get_ticket_remind_time(main_message_id, main_channel_id, user_tag):
		sql = "UPDATE reminded_tickets SET reminded_at=(?) WHERE user_tag=(?) AND main_channel_id=(?) AND main_message_id=(?)"
	else:
		sql = "INSERT INTO reminded_tickets(reminded_at, user_tag, main_channel_id, main_message_id) VALUES (?, ?, ?, ?)"
	CURSOR.execute(sql, (remind_time, user_tag, main_channel_id, main_message_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def get_custom_hashtag(channel_id):
	sql = "SELECT custom_hashtag FROM custom_channel_hashtags WHERE channel_id=(?)"
	CURSOR.execute(sql, (channel_id,))
	result = CURSOR.fetchone()
	if result:
		return result[0]


@db_thread_lock
def is_custom_hashtag_exists(channel_id):
	sql = "SELECT id FROM custom_channel_hashtags WHERE channel_id=(?)"
	CURSOR.execute(sql, (channel_id,))
	result = CURSOR.fetchone()
	return bool(result)


@db_thread_lock
def insert_or_update_custom_hashtag(channel_id, custom_hashtag):
	if is_custom_hashtag_exists(channel_id):
		sql = "UPDATE custom_channel_hashtags SET custom_hashtag=(?) WHERE channel_id=(?)"
	else:
		sql = "INSERT INTO custom_channel_hashtags(custom_hashtag, channel_id) VALUES (?, ?)"
	CURSOR.execute(sql, (custom_hashtag, channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def is_individual_channel_exists(channel_id):
	sql = "SELECT id FROM individual_channel_settings WHERE channel_id=(?)"
	CURSOR.execute(sql, (channel_id,))
	result = CURSOR.fetchone()
	return bool(result)


@db_thread_lock
def get_individual_channel_settings(channel_id):
	sql = "SELECT settings, priorities FROM individual_channel_settings WHERE channel_id=(?)"
	CURSOR.execute(sql, (channel_id,))
	result = CURSOR.fetchone()
	return result


@db_thread_lock
def insert_individual_channel(main_channel_id, channel_id, settings, user_id):
	if is_individual_channel_exists(channel_id):
		return
	sql = "INSERT INTO individual_channel_settings (main_channel_id, channel_id, settings, user_id) VALUES (?, ?, ?, ?)"
	CURSOR.execute(sql, (main_channel_id, channel_id, settings, user_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def update_individual_channel_settings(channel_id, settings):
	sql = "UPDATE individual_channel_settings SET settings=(?) WHERE channel_id=(?)"
	CURSOR.execute(sql, (settings, channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def update_individual_channel(channel_id, settings, priority):
	sql = "UPDATE individual_channel_settings SET settings=(?), priorities=(?) WHERE channel_id=(?)"
	CURSOR.execute(sql, (settings, priority, channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def delete_individual_channel(channel_id):
	sql = "DELETE FROM individual_channel_settings WHERE channel_id=(?)"
	CURSOR.execute(sql, (channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def get_individual_channels_by_priority(main_channel_id, priority):
	sql = '''
		SELECT channel_id, settings FROM individual_channel_settings WHERE main_channel_id=(?) AND
		priorities LIKE '%' || ? || '%'
	'''
	CURSOR.execute(sql, (main_channel_id, priority,))
	result = CURSOR.fetchall()
	if result:
		return result
	else:
		return []


@db_thread_lock
def update_individual_channel_user(channel_id, user_id):
	sql = "UPDATE individual_channel_settings SET user_id=(?) WHERE channel_id=(?)"
	CURSOR.execute(sql, (user_id, channel_id,))
	DB_CONNECTION.commit()


@db_thread_lock
def get_user_individual_channels(main_channel_id, user_id):
	sql = "SELECT channel_id, settings FROM individual_channel_settings WHERE main_channel_id=(?) AND user_id=(?)"
	CURSOR.execute(sql, (main_channel_id, user_id,))
	result = CURSOR.fetchall()
	if result:
		return result
	else:
		return []


@db_thread_lock
def get_tickets_for_reminding(main_channel_id, user_id, user_tag):
	# finds all forwarded tickets from every channel where user is channel's owner
	# that match priority and is opened (scheduled tickets is ignored)
	sql = '''
		SELECT copied_messages.copied_channel_id, copied_messages.copied_message_id, copied_messages.main_channel_id,
		copied_messages.main_message_id, tickets_data.user_tags, tickets_data.priority, tickets_data.update_time,
		reminded_tickets.reminded_at FROM copied_messages LEFT JOIN tickets_data ON
		tickets_data.main_channel_id = copied_messages.main_channel_id AND
		tickets_data.main_message_id = copied_messages.main_message_id
		LEFT JOIN reminded_tickets ON
		reminded_tickets.main_channel_id = copied_messages.main_channel_id AND
		reminded_tickets.main_message_id = copied_messages.main_message_id AND
		reminded_tickets.user_tag = (?)
		WHERE copied_channel_id IN (
			SELECT channel_id FROM individual_channel_settings WHERE user_id = (?) AND main_channel_id = (?)
		) AND copied_messages.main_message_id NOT IN (
			SELECT main_message_id FROM scheduled_messages WHERE main_channel_id = copied_messages.main_channel_id
		) AND tickets_data.is_opened=1;
	'''

	CURSOR.execute(sql, (user_tag, user_id, main_channel_id,))
	result = CURSOR.fetchall()
	return result


@db_thread_lock
def find_copied_message_from_main(main_message_id, main_channel_id, user_id, priority):
	sql = '''
		SELECT copied_message_id, copied_channel_id FROM copied_messages WHERE copied_channel_id IN (
			SELECT channel_id FROM individual_channel_settings WHERE user_id=(?) AND main_channel_id=(?)
			AND priorities LIKE '%' || ? || '%'
		) AND main_message_id=(?) AND main_channel_id=(?)
	'''
	CURSOR.execute(sql, (user_id, main_channel_id, priority, main_message_id, main_channel_id))
	result = CURSOR.fetchone()
	return result


@db_thread_lock
def find_copied_message_in_channel(individual_channel_id, main_message_id):
	sql = "SELECT copied_message_id FROM copied_messages WHERE copied_channel_id = (?) AND main_message_id = (?)"
	CURSOR.execute(sql, (individual_channel_id, main_message_id,))
	result = CURSOR.fetchone()
	if result:
		return result[0]


@db_thread_lock
def get_all_individual_channels(main_channel_id):
	sql = "SELECT channel_id, settings FROM individual_channel_settings WHERE main_channel_id=(?)"
	CURSOR.execute(sql, (main_channel_id,))
	result = CURSOR.fetchall()
	if result:
		return result
	else:
		return []
