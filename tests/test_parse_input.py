import unittest

from wordvault.parse_input import clean_word, parse_input_text


class ParseTests(unittest.TestCase):
    def test_trailing_chinese_removed(self):
        self.assertEqual(clean_word("apple 苹果"), "apple")
        self.assertEqual(clean_word("give up 放弃"), "give up")
        self.assertEqual(clean_word("take care of，照顾"), "take care of")

    def test_batch_formats(self):
        text = "apple, banana\ncherry，date 枣; elderberry；fig 无花果"
        words = parse_input_text(text)
        self.assertEqual(
            words, ["apple", "banana", "cherry", "date", "elderberry", "fig"]
        )

    def test_dedupe_case_insensitive(self):
        words = parse_input_text("Apple, apple, APPLE\nBanana")
        self.assertEqual(words, ["Apple", "Banana"])

    def test_ignores_garbage(self):
        self.assertEqual(parse_input_text("苹果 123 ,,, -"), [])

    def test_phrase_spacing(self):
        self.assertEqual(clean_word("look   forward   to"), "look forward to")

    def test_spaces_are_not_separators(self):
        words = parse_input_text("apple banana")
        self.assertEqual(words, ["apple banana"])

    def test_phrase_with_space_kept(self):
        words = parse_input_text("cater on")
        self.assertEqual(words, ["cater on"])

    def test_phrasal_verb_kept_without_dict(self):
        words = parse_input_text("give up\nput off\nlook forward to")
        self.assertEqual(words, ["give up", "put off", "look forward to"])

    def test_prepositional_phrase_kept(self):
        words = parse_input_text("in the morning")
        self.assertEqual(words, ["in the morning"])


if __name__ == "__main__":
    unittest.main()
