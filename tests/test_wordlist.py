import os
import tempfile
import unittest

from passcheck.wordlist import InputError, iter_words, list_wordlist_files, open_index


class TestWordlist(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.wl = os.path.join(self.dir, "wordlists")
        self.var = os.path.join(self.dir, "var")
        os.makedirs(self.wl)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, text):
        with open(os.path.join(self.wl, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_skip_comments_and_empty(self):
        self._write("a.txt", "# comment\n\nhello\n  \nworld\n")
        words = list(iter_words(list_wordlist_files(self.wl)))
        self.assertEqual(words, ["hello", "  ", "world"])

    def test_filename_order_and_first_spelling_wins(self):
        self._write("b.txt", "Password\npassword\n")
        self._write("a.txt", "PASSWORD\n")
        index = open_index(self.wl, self.var)
        try:
            # a.txt 字典序在前：PASSWORD 先出现
            self.assertEqual(index.lookup("password"), "PASSWORD")
            self.assertIsNone(index.lookup("nope"))
        finally:
            index.close()

    def test_index_reused_and_rebuilt_on_change(self):
        self._write("a.txt", "alpha\n")
        index = open_index(self.wl, self.var)
        index.close()
        self.assertTrue(os.path.exists(os.path.join(self.var, "wordlist-index.sqlite3")))
        # 内容不变：索引复用
        index = open_index(self.wl, self.var)
        self.assertEqual(index.lookup("alpha"), "alpha")
        index.close()
        # 词表变化：重建
        self._write("a.txt", "alpha\nbeta\n")
        index = open_index(self.wl, self.var)
        self.assertEqual(index.lookup("beta"), "beta")
        index.close()
        # 删掉 var/ 也能重建，结果一致
        for name in os.listdir(self.var):
            os.remove(os.path.join(self.var, name))
        index = open_index(self.wl, self.var)
        self.assertEqual(index.lookup("beta"), "beta")
        index.close()

    def test_missing_dir(self):
        with self.assertRaises(InputError):
            list_wordlist_files(os.path.join(self.dir, "nope"))
        with self.assertRaises(InputError):
            list_wordlist_files(self.wl)


if __name__ == "__main__":
    unittest.main()
