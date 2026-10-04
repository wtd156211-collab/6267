"""引擎组合逻辑测试：R2 变体与 span、规则顺序、评分汇总。"""

import unittest

from passcheck.engine import evaluate_password


def lookup_from(words):
    table = {w.lower(): w for w in words}

    def lookup(keys):
        return {k: table[k] for k in keys if k in table}

    return lookup


EMPTY = lookup_from([])


def evaluate(password, username="user01", email="user01@example.com", lookup=EMPTY):
    return evaluate_password(password, username, email, lookup)


class TestR1Only(unittest.TestCase):
    def test_rules_start_with_r1(self):
        res = evaluate("aB3$defghijklmno")
        self.assertEqual(res["rules"][0], {"rule": "R1", "base": 91, "span": [0, 16]})
        self.assertTrue(res["passed"])
        self.assertEqual(res["score"], 91)

    def test_low_score_not_passed(self):
        res = evaluate("Abcd1!xy")
        self.assertFalse(res["passed"])
        self.assertEqual(res["score"], 59)


class TestR2Variants(unittest.TestCase):
    def test_exact_keeps_wordlist_spelling(self):
        res = evaluate("Password1!", lookup=lookup_from(["Password1!"]))
        r2 = res["rules"][1]
        self.assertEqual(r2["term"], "Password1!")
        self.assertEqual(r2["variant"], "原样")
        self.assertEqual(r2["span"], [0, 10])
        self.assertFalse(res["passed"])

    def test_case_falls_into_exact(self):
        res = evaluate("PASSWORD", lookup=lookup_from(["password"]))
        self.assertEqual(res["rules"][1]["variant"], "原样")

    def test_trim_variant_span(self):
        res = evaluate("2024monkey", lookup=lookup_from(["monkey"]))
        r2 = res["rules"][1]
        self.assertEqual(r2["variant"], "去前后缀")
        self.assertEqual(r2["span"], [4, 10])

    def test_fold_variant(self):
        res = evaluate("p@ssw0rd", lookup=lookup_from(["password"]))
        r2 = res["rules"][1]
        self.assertEqual(r2["variant"], "形近替换")
        self.assertEqual(r2["span"], [0, 8])

    def test_trim_then_fold_variant(self):
        res = evaluate("P@ssw0rd2024!", lookup=lookup_from(["password"]))
        r2 = res["rules"][1]
        self.assertEqual(r2["variant"], "去前后缀+形近替换")
        self.assertEqual(r2["span"], [0, 8])

    def test_first_key_order_wins(self):
        # 原样命中优先于去前后缀
        res = evaluate("factory2024", lookup=lookup_from(["factory2024", "factory"]))
        r2 = res["rules"][1]
        self.assertEqual(r2["variant"], "原样")
        self.assertEqual(r2["term"], "factory2024")

    def test_no_substring_match(self):
        res = evaluate("passwordz", lookup=lookup_from(["password"]))
        self.assertEqual(len(res["rules"]), 1)

    def test_high_score_still_vetoed(self):
        res = evaluate("Riverstone#2024", lookup=lookup_from(["riverstone"]))
        self.assertEqual(res["score"], 87)
        self.assertFalse(res["passed"])

    def test_unicode_lower_length_change_span(self):
        # 'İ'.lower() 为两个码点，span 仍按原口令码点计
        res = evaluate("1İabc1", lookup=lookup_from(["i̇abc"]))
        r2 = res["rules"][1]
        self.assertEqual(r2["variant"], "去前后缀")
        self.assertEqual(r2["span"], [1, 5])


class TestR3(unittest.TestCase):
    def test_seq_keeps_original_case(self):
        res = evaluate("QwErTyUi")
        r3 = res["rules"][1]
        self.assertEqual(r3["seq"], "QwErTyUi")
        self.assertEqual(r3["span"], [0, 8])
        self.assertFalse(res["passed"])

    def test_no_hit_under_four(self):
        res = evaluate("wsx")
        self.assertEqual(len(res["rules"]), 1)


class TestR4(unittest.TestCase):
    def test_whole_password(self):
        res = evaluate("ababab")
        r4 = res["rules"][1]
        self.assertEqual((r4["unit"], r4["repeat"], r4["span"]), ("ab", 3, [0, 6]))

    def test_trimmed_candidate(self):
        res = evaluate("1aaaa1")
        r4 = res["rules"][1]
        self.assertEqual((r4["unit"], r4["repeat"], r4["span"]), ("a", 4, [1, 5]))

    def test_two_repeats_not_enough(self):
        res = evaluate("qweqwe")
        self.assertEqual(len(res["rules"]), 1)


class TestSummary(unittest.TestCase):
    def test_multiple_rules_all_reported(self):
        res = evaluate("qwerty123", lookup=lookup_from(["qwerty123"]))
        kinds = [r["rule"] for r in res["rules"]]
        self.assertEqual(kinds, ["R1", "R2", "R3"])

    def test_deduct_reduces_score(self):
        res = evaluate(
            "zhang.wei2024", "zhang.wei", "zhang.wei@example.com"
        )
        self.assertEqual(res["score"], 70 - 20)
        r5 = res["rules"][1]
        self.assertEqual(r5["level"], "扣")
        self.assertIsNone(r5["span"])

    def test_reject_level_vetoes(self):
        res = evaluate("Zhang.Wei", "zhang.wei", "zhang.wei@example.com")
        self.assertFalse(res["passed"])
        self.assertEqual(res["score"], 54)

    def test_score_floor_zero(self):
        res = evaluate("zhang.wei", "zhang.wei", "zhang.wei@example.com")
        self.assertEqual(res["score"], 45 - 20 + 20)  # 无扣级
        res2 = evaluate("zhangwei", "zhang.wei", "zhang.wei@example.com")
        self.assertEqual(res2["score"], 32)


if __name__ == "__main__":
    unittest.main()
