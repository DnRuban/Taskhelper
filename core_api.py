import logging

from pyrogram import Client
from config_utils import BOT_TOKEN, APP_API_ID, APP_API_HASH

app = Client(
	"pyrogram_bot",
	api_id=APP_API_ID, api_hash=APP_API_HASH,
	bot_token=BOT_TOKEN
)


def core_api_function(func):
	def inner_function(*args, **kwargs):
		if not app.is_initialized:
			logging.info("Starting pyrogram client")
			app.start()
		return func(*args, **kwargs)
	return inner_function


def close_client():
	if app.is_initialized:
		logging.info("Closing pyrogram client")
		app.stop(True)


@core_api_function
def get_messages(chat_id, message_ids):
	return app.get_messages(chat_id, message_ids)


@core_api_function
def get_user(identifier):
	try:
		return app.get_users(identifier)
	except Exception as E:
		logging.info(f"Core api get_user({identifier}) exception: {E}")

