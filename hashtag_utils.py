from typing import List

import telebot
from telebot.types import MessageEntity


def insert_hashtag_in_post(text: str, entities: List[telebot.types.MessageEntity], hashtag: str, position: int):
	hashtag_text = hashtag
	if len(text) > position:
		hashtag_text += " "

	text = text[:position] + hashtag_text + text[position:]

	if entities is None:
		entities = []

	for entity in entities:
		if entity.offset >= position:
			entity.offset += len(hashtag_text)

	entity_length = hashtag.find(" ") if " " in hashtag else len(hashtag)

	hashtag_entity = MessageEntity(type="hashtag", offset=position, length=entity_length)
	entities.append(hashtag_entity)
	entities.sort(key=lambda e: e.offset)

	return text, entities
