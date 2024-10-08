import logging

from pyrogram import Client, utils
from config_utils import BOT_TOKEN, APP_API_ID, APP_API_HASH

'''
This is a fix for get_peer_type in Pyrogram module.
Original function throws an exception if channel id is less than -1002147483647.
This fix should be removed after this bug is fixed in Pyrogram module.
Issue with this bug: https://github.com/pyrogram/pyrogram/issues/1314
'''
def get_peer_type_fixed(peer_id: int) -> str:
	if peer_id < 0:
		if -999999999999 <= peer_id:
			return "chat"
		if -1997852516352 <= peer_id < -1000000000000:
			return "channel"
	elif 0 < peer_id <= 0xffffffffff:
		return "user"

	raise ValueError(f"Peer id invalid: {peer_id}")

# replace original function with fixed version
utils.get_peer_type = get_peer_type_fixed

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
