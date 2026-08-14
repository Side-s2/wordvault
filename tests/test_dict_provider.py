import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wordvault.db import Meaning
from wordvault.dict_provider import (
    DictProvider,
    parse_translation_lines,
    split_pos,
    uk_phonetic,
)


class ParseTests(unittest.TestCase):
    def test_split_pos(self):
        self.assertEqual(split_pos("n. 苹果"), ("n.", "苹果"))
        self.assertEqual(split_pos("[计] 苹果电脑"), ("[计]", "苹果电脑"))
        self.assertEqual(split_pos("苹果"), ("", "苹果"))

    def test_ecdict_lines(self):
        meanings = parse_translation_lines(
            "n. 苹果；苹果树\n[计] 苹果公司\nvt. 使…高兴"
        )
        texts = [(m.pos, m.text) for m in meanings]
        self.assertIn(("n.", "苹果"), texts)
        self.assertIn(("n.", "苹果树"), texts)
        self.assertIn(("[计]", "苹果公司"), texts)

    def test_uk_phonetic_only(self):
        self.assertEqual(uk_phonetic("英 /əˈpəl/ 美 /ˈæpəl/"), "/əˈpəl/")
        self.assertEqual(uk_phonetic("/əˈpəl/"), "/əˈpəl/")
        self.assertEqual(uk_phonetic(""), "")


def make_offline_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE stardict (word TEXT, phonetic TEXT, translation TEXT, "
        "definition TEXT)"
    )
    conn.execute(
        "INSERT INTO stardict VALUES (?, ?, ?, ?)",
        (
            "apple",
            "[ˈæpl]",
            "n. 苹果；苹果树",
            "the fruit of an apple tree",
        ),
    )
    conn.commit()
    conn.close()


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dict_path = Path(self.tmp.name) / "dict.db"
        make_offline_db(self.dict_path)
        self.provider = DictProvider(self.dict_path)

    def tearDown(self):
        self.provider.close()
        self.tmp.cleanup()

    def test_offline_hit_no_network(self):
        with mock.patch("wordvault.dict_provider.requests.get") as get:
            result = self.provider.lookup("apple", want_examples=False)
            get.assert_not_called()
        self.assertEqual(result.source, "offline")
        self.assertEqual(result.phonetic, "[ˈæpl]")
        self.assertEqual(result.meanings[0], Meaning(pos="n.", text="苹果"))

    def test_offline_miss_goes_online(self):
        fake = mock.Mock()
        fake.status_code = 200
        fake.json.return_value = {
            "ec": {
                "word": {
                    "usphone": "ˈhɛloʊ",
                    "ukphone": "həˈləʊ",
                    "trs": [{"tr": [{"l": {"i": ["int. 你好；喂"]}}]}],
                }
            },
            "blng_sents_part": {
                "sentence-pair": [
                    {
                        "sentence": "Hello, world!",
                        "sentence-translation": "你好，世界！",
                    }
                ]
            },
        }
        with mock.patch(
            "wordvault.dict_provider.requests.get", return_value=fake
        ):
            result = self.provider.lookup("hello", want_examples=True)
        self.assertEqual(result.source, "online")
        self.assertEqual(result.meanings[0].pos, "int.")
        self.assertEqual(result.examples[0].zh, "你好，世界！")
        self.assertIn("/həˈləʊ/", result.phonetic)

    def test_full_miss_returns_none_source(self):
        fake = mock.Mock()
        fake.status_code = 200
        fake.json.side_effect = [
            {"ec": {}},
            {
                "responseData": {
                    "translatedText": "ZZZQWERTY123",
                    "responseStatus": 200,
                }
            },
        ]
        with mock.patch(
            "wordvault.dict_provider.requests.get", return_value=fake
        ):
            result = self.provider.lookup("zzzqwerty123")
        self.assertEqual(result.source, "none")
        self.assertFalse(result.ok)

    def test_phrase_uses_web_trans(self):
        fake = mock.Mock()
        fake.status_code = 200
        fake.json.return_value = {
            "ec": {
                "word": [
                    {
                        "usphone": "ɡɪv ʌp",
                        "trs": [{"tr": [{"l": {"i": ["放弃：指停止做某事"]}}]}],
                    }
                ]
            },
            "web_trans": {
                "web-translation": [
                    {
                        "key": "give up",
                        "trans": [
                            {"value": "停止"},
                            {"value": "投降"},
                            {"value": "抛弃"},
                        ],
                    }
                ]
            },
            "blng_sents_part": {"sentence-pair": []},
        }
        with mock.patch(
            "wordvault.dict_provider.requests.get", return_value=fake
        ):
            result = self.provider.lookup("give up", want_examples=True)
        self.assertEqual(result.source, "online")
        self.assertEqual(
            [m.text for m in result.meanings], ["停止", "投降", "抛弃"]
        )


if __name__ == "__main__":
    unittest.main()
