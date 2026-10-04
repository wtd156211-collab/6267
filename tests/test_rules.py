"""R1/R3/R4/R5 与字符工具的单元测试（合成数据，不读文件）。"""

import unittest

from passcheck.rules import (
    base_score,
    char_class,
    fold,
    keyboard_run,
    levenshtein,
    repeat_unit,
    trim_bounds,
    user_similarity,
)


class TestCharTools(unittest.TestCase):
    def test_char_class(self):
        self.assertEqual(char_class("a"), "L")
        self.assertEqual(char_class("Z"), "U")
        self.assertEqual(char_class("7"), "D")
        self.assertEqual(char_class("!"), "S")
        self.assertEqual(char_class("@"), "S")
        self.assertEqual(char_class("~"), "S")
        self.assertEqual(char_class("蓝"), "O")
        self.assertEqual(char_class(" "), "O")

    def test_fold(self):
        self.assertEqual(fold("p@ssw0rd"), "password")
        self.assertEqual(fold("F4ct0ry"), "Factory")
        self.assertEqual(fold("1234567890"), "izeasgtbgo")
        self.assertEqual(fold("$!+"), "sit")
        self.assertEqual(fold("abc"), "abc")

    def test_trim_bounds(self):
        self.assertEqual(trim_bounds("abc"), (0, 0))
        self.assertEqual(trim_bounds("1abc!"), (1, 1))
        self.assertEqual(trim_bounds("!!2024!!"), (8, 0))
        self.assertEqual(trim_bounds("123"), (3, 0))
        self.assertEqual(trim_bounds(""), (0, 0))


class TestBaseScore(unittest.TestCase):
    def test_under_eight_is_zero(self):
        self.assertEqual(base_score("Ab1!xyz"), 0)
        self.assertEqual(base_score(""), 0)

    def test_formula(self):
        # n=8, k=4 -> 32 + 27
        self.assertEqual(base_score("Abcd1!xy"), 59)
        # n 超过 16 按 16 计
        self.assertEqual(base_score("aB3$defghijklmno"), 91)
        # 单一类别
        self.assertEqual(base_score("abcdefghijklmno"), 60)
        # 上限 100（需要五类齐全）
        self.assertEqual(base_score("aB1$蓝" * 7), 100)
        # 其它类别计入 k
        self.assertEqual(base_score("蓝色#星河7号站台"), 54)


class TestKeyboardRun(unittest.TestCase):
    def test_forward_and_backward(self):
        self.assertEqual(keyboard_run("qwerty"), (0, 6))
        self.assertEqual(keyboard_run("poiuyt"), (0, 6))
        self.assertEqual(keyboard_run("lkjhgf"), (0, 6))

    def test_min_length_four(self):
        self.assertIsNone(keyboard_run("qwe"))
        self.assertIsNone(keyboard_run("asd"))
        self.assertEqual(keyboard_run("asdf"), (0, 4))

    def test_embedded_and_digits(self):
        self.assertEqual(keyboard_run("xxqwertyxx"), (2, 8))
        self.assertEqual(keyboard_run("ab1234cd"), (2, 6))
        self.assertEqual(keyboard_run("0123456789"), (1, 10))

    def test_longest_then_earliest(self):
        # 两个等长行走，取起点最小
        self.assertEqual(keyboard_run("qwertyxxasdfg"), (0, 6))
        # 更长的优先
        self.assertEqual(keyboard_run("asdfxxqwertyu"), (6, 13))

    def test_same_start_prefers_forward(self):
        # 起点 0 处正反向都到不了 4；整体不命中
        self.assertIsNone(keyboard_run("tqw"))
        # 正向与反向等长并列时正向优先（结果区间一致，序列取自原串）

    def test_no_wiggle(self):
        # 来回拐弯不算（行走必须单调）
        self.assertIsNone(keyboard_run("qwqw"))
        self.assertIsNone(keyboard_run("qwew"))

    def test_shifted_symbols_not_matched(self):
        self.assertIsNone(keyboard_run("!@#$"))
        self.assertIsNone(keyboard_run("1qaz2wsx"))


class TestRepeatUnit(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(repeat_unit("aaaaaa"), ("a", 6))
        self.assertEqual(repeat_unit("ababab"), ("ab", 3))
        self.assertEqual(repeat_unit("abcabcabc"), ("abc", 3))

    def test_smallest_m_wins(self):
        self.assertEqual(repeat_unit("12121212"), ("12", 4))
        self.assertEqual(repeat_unit("aaaaaaaa"), ("a", 8))

    def test_repeat_at_least_three(self):
        self.assertIsNone(repeat_unit("qweqwe"))
        self.assertIsNone(repeat_unit("abab"))

    def test_negative(self):
        self.assertIsNone(repeat_unit("abcabcab"))
        self.assertIsNone(repeat_unit("aabbaabb"))
        self.assertIsNone(repeat_unit(""))


class TestLevenshtein(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(levenshtein("", ""), 0)
        self.assertEqual(levenshtein("abc", "abc"), 0)
        self.assertEqual(levenshtein("abc", "abd"), 1)
        self.assertEqual(levenshtein("abc", "abcd"), 1)
        self.assertEqual(levenshtein("kitten", "sitting"), 3)
        self.assertEqual(levenshtein("zhang.wei2024", "zhang.wei"), 4)


class TestUserSimilarity(unittest.TestCase):
    def test_reject_level(self):
        r = user_similarity("zhang.wei", "zhang.wei", "zhang.wei@example.com")
        self.assertEqual(r["level"], "拒")
        self.assertEqual(r["cand"], "username")
        self.assertEqual((r["dist"], r["max_len"]), (0, 9))
        self.assertIsNone(r["span"])

    def test_deduct_level(self):
        r = user_similarity("zhang.wei2024", "zhang.wei", "zhang.wei@example.com")
        self.assertEqual(r["level"], "扣")
        self.assertEqual((r["dist"], r["max_len"]), (4, 13))

    def test_no_entry(self):
        self.assertIsNone(user_similarity("lina2024", "lina", "li.na@corp.example.net"))

    def test_email_local_candidate(self):
        r = user_similarity("li.na", "lina", "li.na@corp.example.net")
        self.assertEqual(r["cand"], "email-local")
        self.assertEqual(r["level"], "拒")

    def test_best_ratio_wins(self):
        # email-local 完全相等，优于 username 的 4/13
        r = user_similarity("wangqiang1988", "wangqiang", "wangqiang1988@mail.example.org")
        self.assertEqual(r["cand"], "email-local")
        self.assertEqual(r["dist"], 0)

    def test_case_insensitive(self):
        r = user_similarity("zhang.wei", "Zhang.Wei", "ZHANG.WEI@EXAMPLE.COM")
        self.assertEqual(r["dist"], 0)

    def test_empty_candidates_skipped(self):
        self.assertIsNone(user_similarity("abc", "", ""))
        self.assertIsNone(user_similarity("abc", "@", "@"))


if __name__ == "__main__":
    unittest.main()
