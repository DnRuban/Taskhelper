from unittest import TestCase, main
from unittest.mock import patch

from hashtag_data import HashtagData
import test_helper


@patch("hashtag_data.PRIORITY_TAG", "p")
@patch("hashtag_data.OPENED_TAG", "o")
class FindMentionedUsersTest(TestCase):
	@patch("db_utils.is_user_tag_exists")
	@patch("hashtag_data.HashtagData.__init__")
	def test_find_mentioned_users(self, mock_hashtag_data_init, mock_is_user_tag_exists):
		mock_hashtag_data_init.return_value = None

		user_tags = ["aa", "bb", "cc"]
		is_user_tag = lambda channel_id, user_tag: user_tag in user_tags
		mock_is_user_tag_exists.side_effect = is_user_tag

		text = f"text #aa #bb\n#o #cc #p #user_tag"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		hashtag_data.hashtag_indexes = [None, 2, [3], 4]
		hashtag_data.main_channel_id = main_channel_id
		result = hashtag_data.find_mentioned_users(post_data)
		self.assertEqual(result, ["aa", "bb"])

	@patch("db_utils.is_user_tag_exists")
	@patch("hashtag_data.HashtagData.__init__")
	def test_no_mentioned_users(self, mock_hashtag_data_init, mock_is_user_tag_exists):
		mock_hashtag_data_init.return_value = None

		user_tags = ["cc"]
		is_user_tag = lambda channel_id, user_tag: user_tag in user_tags
		mock_is_user_tag_exists.side_effect = is_user_tag

		text = f"text test\n#o #cc #p #user_tag"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)

		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		hashtag_data.hashtag_indexes = [None, 0, [1], 2]
		hashtag_data.main_channel_id = main_channel_id
		result = hashtag_data.find_mentioned_users(post_data)
		self.assertEqual(result, [])


class GetEntitiesToIgnoreTest(TestCase):
	@patch("hashtag_data.HashtagData.__init__")
	def test_middle_and_back_entities(self, mock_hashtag_data_init):
		mock_hashtag_data_init.return_value = None

		text = f"text #aa #bb\n#o #cc #p #user_tag"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		result = hashtag_data.get_entities_to_ignore(text, entities)
		self.assertEqual(result, range(0, 2))

	@patch("hashtag_data.HashtagData.__init__")
	def test_front_entities(self, mock_hashtag_data_init):
		mock_hashtag_data_init.return_value = None

		text = f"#aa #bb test #cc test"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		result = hashtag_data.get_entities_to_ignore(text, entities)
		self.assertEqual(result, range(2, 3))

	@patch("hashtag_data.HashtagData.__init__")
	def test_back_entities(self, mock_hashtag_data_init):
		mock_hashtag_data_init.return_value = None

		text = f"test text\n#o #cc #p #user_tag"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		result = hashtag_data.get_entities_to_ignore(text, entities)
		self.assertEqual(result, range(0, 0))

	@patch("hashtag_data.HashtagData.__init__")
	def test_middle_and_front_entities(self, mock_hashtag_data_init):
		mock_hashtag_data_init.return_value = None

		text = f"#o #cc #p test #aa #bb text"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		result = hashtag_data.get_entities_to_ignore(text, entities)
		self.assertEqual(result, range(3, 5))

	@patch("hashtag_data.HashtagData.__init__")
	def test_end_of_line_entities(self, mock_hashtag_data_init):
		mock_hashtag_data_init.return_value = None

		text = f"#aa text #bb #user_tag"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		result = hashtag_data.get_entities_to_ignore(text, entities)
		self.assertEqual(result, range(1, 3))


class RemoveDuplicatesTest(TestCase):
	priority_side_effect = lambda text, entities: (text, entities)
	status_side_effect = lambda text, entities: (text, entities)

	@patch("hashtag_data.HashtagData.remove_redundant_priority_tags", side_effect=priority_side_effect)
	@patch("hashtag_data.HashtagData.remove_redundant_status_tags", side_effect=status_side_effect)
	@patch("hashtag_data.HashtagData.__init__", return_value=None)
	def test_remove_user_tag_duplicates(self, *args):
		text = f"text\n#aa #bb #cc #aa #bb"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		hashtag_data.main_channel_id = main_channel_id
		result = hashtag_data.remove_duplicates(post_data)
		self.assertEqual(result.text, "text\n#aa #bb #cc")


@patch("hashtag_data.POSSIBLE_PRIORITIES", ["1", "2", "3"])
@patch("hashtag_data.PRIORITY_TAG", "p")
class RemoveRedundantPriorityTagsTest(TestCase):
	@patch("hashtag_data.HashtagData.get_priority_number_or_default", return_value="1")
	@patch("hashtag_data.HashtagData.__init__", return_value=None)
	def test_same_priority_tags(self, *args):
		text = f"text\n#aa #bb #p1 #p1"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		hashtag_data.main_channel_id = main_channel_id
		hashtag_data.hashtag_indexes = [None, None, [], 0]
		result = hashtag_data.remove_redundant_priority_tags(text, entities)
		self.assertEqual(result[0], f"text\n#aa #bb #p1")

	@patch("hashtag_data.HashtagData.get_priority_number_or_default", return_value="1")
	@patch("hashtag_data.HashtagData.__init__", return_value=None)
	def test_different_priority_tags(self, *args):
		text = f"text\n#aa #bb #p2 #p3 #p1"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		hashtag_data.main_channel_id = main_channel_id
		hashtag_data.hashtag_indexes = [None, None, [], 0]
		result = hashtag_data.remove_redundant_priority_tags(text, entities)
		self.assertEqual(result[0], f"text\n#aa #bb #p1")


@patch("hashtag_data.PRIORITY_TAG", "p")
@patch("hashtag_data.OPENED_TAG", "o")
@patch("hashtag_data.CLOSED_TAG", "x")
class RemoveRedundantStatusTagsTest(TestCase):
	@patch("hashtag_data.HashtagData.is_scheduled", return_value=False)
	@patch("hashtag_data.HashtagData.__init__", return_value=None)
	def test_same_status_tags(self, *args):
		text = f"text\n#o #o #aa #bb #p1 #o"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		hashtag_data.main_channel_id = main_channel_id
		result = hashtag_data.remove_redundant_status_tags(text, entities)
		self.assertEqual(result[0], f"text\n#o #aa #bb #p1")

	@patch("hashtag_data.HashtagData.is_scheduled", return_value=False)
	@patch("hashtag_data.HashtagData.__init__", return_value=None)
	def test_different_status_tags(self, *args):
		text = f"text\n#x #o #x #aa #bb #p1"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		hashtag_data.main_channel_id = main_channel_id
		result = hashtag_data.remove_redundant_status_tags(text, entities)
		self.assertEqual(result[0], f"text\n#o #aa #bb #p1")


@patch("hashtag_data.PRIORITY_TAG", "p")
@patch("hashtag_data.OPENED_TAG", "o")
@patch("hashtag_data.CLOSED_TAG", "x")
@patch("hashtag_data.SCHEDULED_TAG", "s")
class RemoveRedundantScheduledTagsTest(TestCase):
	def update_scheduled_tag_entities_length(self, scheduled_tag, text, entities):
		for entity in entities:
			entity_text = text[entity.offset : entity.offset + entity.length]
			if entity_text != scheduled_tag:
				continue

			text_after_tag = text[entity.offset:]
			scheduled_tag_parts = text_after_tag.split(" ")[:3]
			if len(scheduled_tag_parts) < 3:
				continue
			full_tag_length = len(" ".join(scheduled_tag_parts))
			entity.length = full_tag_length

	@patch("hashtag_data.HashtagData.__init__", return_value=None)
	def test_identical_scheduled_tags(self, *args):
		text = "text\n#o #aa #bb #p1 #s 2023-06-25 17:00 #s 2023-06-25 17:00"
		entities = test_helper.create_hashtag_entity_list(text)
		self.update_scheduled_tag_entities_length("#s", text, entities)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		hashtag_data.main_channel_id = main_channel_id
		hashtag_data.scheduled_tag = None
		result = hashtag_data.remove_redundant_scheduled_tags(text, entities)
		self.assertEqual(result[0], "text\n#o #aa #bb #p1 #s 2023-06-25 17:00")

	@patch("hashtag_data.HashtagData.__init__", return_value=None)
	def test_scheduled_tags_without_date(self, *args):
		text = "text\n#o #aa #bb #p1 #s #s"
		entities = test_helper.create_hashtag_entity_list(text)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		hashtag_data.main_channel_id = main_channel_id
		result = hashtag_data.remove_redundant_scheduled_tags(text, entities)
		self.assertEqual(result[0], "text\n#o #aa #bb #p1")
		self.assertIsNone(hashtag_data.scheduled_tag)

	@patch("hashtag_data.HashtagData.__init__", return_value=None)
	def test_partial_scheduled_tag(self, *args):
		text = "text\n#o #aa #bb #p1 #s 2023-06-25"
		entities = test_helper.create_hashtag_entity_list(text)
		self.update_scheduled_tag_entities_length("#s", text, entities)
		post_data = test_helper.create_mock_message(text, entities)
		main_channel_id = 123

		hashtag_data = HashtagData(post_data, main_channel_id)
		hashtag_data.main_channel_id = main_channel_id
		result = hashtag_data.remove_redundant_scheduled_tags(text, entities)
		self.assertEqual(result[0], "text\n#o #aa #bb #p1 #s 2023-06-25")


@patch("hashtag_data.SCHEDULED_TAG", "s")
@patch("hashtag_data.SCHEDULED_DATE_FORMAT_REGEX", "^\d{4}-\d{1,2}-\d{1,2}")
@patch("hashtag_data.SCHEDULED_TIME_FORMAT_REGEX", "^\d{1,2}:\d{1,2}")
class UpdateScheduledTagTest(TestCase):
	def test_update_entity(self, *args):
		text = "#s 2023-06-25 17:00"
		entities = test_helper.create_hashtag_entity_list(text)

		result = HashtagData.update_scheduled_tag(text, entities, 0)
		self.assertTrue(result)
		self.assertEqual(entities[0].length, len(text))

	def test_not_scheduled_tag(self, *args):
		text = "#test 2023-06-25 17:00"
		entities = test_helper.create_hashtag_entity_list(text)

		entity_length = entities[0].length
		result = HashtagData.update_scheduled_tag(text, entities, 0)
		self.assertFalse(result)
		self.assertEqual(entities[0].length, entity_length)

	def test_incomplete_scheduled_tag(self, *args):
		text = "#s 2023-06-25"
		entities = test_helper.create_hashtag_entity_list(text)

		result = HashtagData.update_scheduled_tag(text, entities, 0)
		self.assertFalse(result)
		self.assertEqual(entities[0].length, len(text))


if __name__ == "__main__":
	main()
