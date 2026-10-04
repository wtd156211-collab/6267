"""词表索引测试：精确查询、大小写去重、内容绑定重建。"""

import os
import tempfile
import unittest

from passcheck.wordlist import WordlistError, WordlistIndex, list_wordlists


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


class WordlistCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.wdir = os.path.join(self.dir, "wordlists")
        os.makedirs(self.wdir)
        self.index_path = os.path.join(self.dir, "var", "wordlist-index.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def open_index(self):
        index = WordlistIndex(self.index_path)
        index.open(list_wordlists(self.wdir))
        return index


class TestListing(WordlistCase):
    def test_missing_dir(self):
        with self.assertRaises(WordlistError):
            list_wordlists(os.path.join(self.dir, "nope"))

    def test_empty_dir(self):
        with self.assertRaises(WordlistError):
            list_wordlists(self.wdir)

    def test_sorted_by_filename(self):
        write(os.path.join(self.wdir, "b.txt"), "x\n")
        write(os.path.join(self.wdir, "a.txt"), "y\n")
        names = [os.path.basename(p) for p in list_wordlists(self.wdir)]
        self.assertEqual(names, ["a.txt", "b.txt"])


class TestIndex(WordlistCase):
    def test_exact_lookup(self):
        write(os.path.join(self.wdir, "w.txt"), "password\nMonkey\n")
        with self.open_index() as index:
            hits = index.lookup(["password", "monkey", "nope"])
        self.assertEqual(hits, {"password": "password", "monkey": "Monkey"})

    def test_case_dedupe_keeps_first_spelling(self):
        write(os.path.join(self.wdir, "a.txt"), "Password\n")
        write(os.path.join(self.wdir, "b.txt"), "password\nPASSWORD\n")
        with self.open_index() as index:
            self.assertEqual(index.lookup(["password"]), {"password": "Password"})

    def test_skips_blank_and_comment_lines(self):
        write(os.path.join(self.wdir, "w.txt"), "# comment\n\nword\n#x\n")
        with self.open_index() as index:
            self.assertEqual(index.lookup(["word", "# comment", ""]), {"word": "word"})

    def test_rebuild_only_when_content_changes(self):
        path = os.path.join(self.wdir, "w.txt")
        write(path, "alpha\n")
        index = self.open_index()
        index.close()
        # 内容不变：复用
        index = WordlistIndex(self.index_path)
        self.assertFalse(index.open(list_wordlists(self.wdir)))
        index.close()
        # 内容变化：重建
        write(path, "alpha\nbeta\n")
        index = WordlistIndex(self.index_path)
        self.assertTrue(index.open(list_wordlists(self.wdir)))
        self.assertEqual(index.lookup(["beta"]), {"beta": "beta"})
        index.close()

    def test_delete_index_keeps_results(self):
        write(os.path.join(self.wdir, "w.txt"), "gamma\n")
        with self.open_index() as index:
            before = index.lookup(["gamma"])
        os.remove(self.index_path)
        with self.open_index() as index:
            self.assertEqual(index.lookup(["gamma"]), before)

    def test_no_false_hits(self):
        write(os.path.join(self.wdir, "w.txt"), "password\n")
        with self.open_index() as index:
            self.assertEqual(index.lookup(["password1", "passwor", "PASSWORD "]), {})


if __name__ == "__main__":
    unittest.main()
