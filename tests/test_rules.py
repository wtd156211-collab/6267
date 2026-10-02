import random
import unittest

from passcheck import rules


def naive_levenshtein(a, b):
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


class TestChars(unittest.TestCase):
    def test_fold(self):
        self.assertEqual(rules.fold("p@ssw0rd"), "password")
        self.assertEqual(rules.fold("F4ct0ry"), "Factory")  # fold 不做小写折叠
        self.assertEqual(rules.fold("98765"), "gbtgs")

    def test_trim_span(self):
        self.assertEqual(rules.trim_span("abc"), (0, 3))
        self.assertEqual(rules.trim_span("1abc!"), (1, 4))
        self.assertEqual(rules.trim_span("!!!1"), (4, 4))
        self.assertEqual(rules.trim_span("abc123"), (0, 3))
        self.assertEqual(rules.trim_span("Zxcv"), (0, 4))


class TestR1(unittest.TestCase):
    def check(self, password):
        return rules.rule_r1(password)

    def test_short_is_zero(self):
        self.assertEqual(self.check("Ab1!xyz")["base"], 0)  # n=7
        self.assertEqual(self.check("Ab1!xy")["base"], 0)

    def test_eight_char_line(self):
        self.assertEqual(self.check("abcdefgh")["base"], 32)  # 8*4
        self.assertEqual(self.check("Abcd1!xy")["base"], 59)  # 32 + 3*9

    def test_categories(self):
        # 大写+小写+数字+符号，n=8
        self.assertEqual(self.check("Zq7&Km2#")["base"], 59)

    def test_cap(self):
        self.assertEqual(self.check("a" * 40)["base"], 64)  # 16*4
        # 4 类封顶 64+27=91；5 类（含 O）才能顶到 100
        p = "Zq7&Km2#Vt9!Rs4Wp6"
        self.assertEqual(len(p), 18)
        self.assertEqual(self.check(p)["base"], 91)
        self.assertEqual(self.check(p + "蓝")["base"], 100)

    def test_unicode_is_other(self):
        # 蓝色#星河7号站台：n=9，O + S + D = 3 类 -> 36+18
        entry = self.check("蓝色#星河7号站台")
        self.assertEqual(entry["base"], 54)
        self.assertEqual(entry["span"], [0, 9])


class TestR2(unittest.TestCase):
    def run_case(self, password):
        table = {
            "password": "password",
            "letmein": "letmein",
            "monkey": "Monkey",
            "factory!": "factory!",
        }
        return rules.rule_r2(password, table.get)

    def test_exact_and_case(self):
        self.assertEqual(self.run_case("password")["variant"], "原样")
        self.assertEqual(self.run_case("PASSWORD")["term"], "password")
        self.assertEqual(self.run_case("Password")["variant"], "原样")

    def test_trim(self):
        hit = self.run_case("!letmein!")
        self.assertEqual(hit["variant"], "去前后缀")
        self.assertEqual(hit["span"], [1, 8])
        self.assertEqual(hit["term"], "letmein")

    def test_fold(self):
        hit = self.run_case("p@ssw0rd")
        self.assertEqual(hit["variant"], "形近替换")
        self.assertEqual(hit["term"], "password")
        self.assertEqual(hit["span"], [0, 8])

    def test_trim_fold_order(self):
        # 5unsh1ne! 先 trim（首 5 也是 D）得 unsh1ne，再 fold 也不等于词表
        table = {"sunshine": "sunshine"}
        self.assertIsNone(rules.rule_r2("5unsh1ne!", table.get))
        # 去前后缀+形近替换
        hit = rules.rule_r2("1M0nkey!", {"monkey": "Monkey"}.get)
        self.assertEqual(hit["variant"], "去前后缀+形近替换")
        self.assertEqual(hit["span"], [1, 7])
        self.assertEqual(hit["term"], "Monkey")

    def test_first_key_wins(self):
        # 原样与 trim 同串时只查一次；原样命中优先
        table = {"abc": "ABC"}
        hit = rules.rule_r2("abc", table.get)
        self.assertEqual(hit["variant"], "原样")

    def test_negative(self):
        self.assertIsNone(self.run_case("passwordz"))
        self.assertIsNone(self.run_case(""))


class TestR3(unittest.TestCase):
    def test_forward_and_reverse(self):
        self.assertEqual(rules.rule_r3("qwerty")["seq"], "qwerty")
        self.assertEqual(rules.rule_r3("poiuyt")["seq"], "poiuyt")
        self.assertEqual(rules.rule_r3("lkjhgf")["seq"], "lkjhgf")
        self.assertEqual(rules.rule_r3("mnbvcx")["seq"], "mnbvcx")

    def test_digit_row(self):
        hit = rules.rule_r3("x1234y")
        self.assertEqual(hit["seq"], "1234")
        self.assertEqual(hit["span"], [1, 5])
        hit = rules.rule_r3("987654321")
        self.assertEqual(hit["seq"], "987654321")

    def test_boundary_length(self):
        self.assertIsNone(rules.rule_r3("qwe"))
        self.assertIsNone(rules.rule_r3("asd"))
        self.assertEqual(rules.rule_r3("asdf")["seq"], "asdf")

    def test_case_folded_original_seq(self):
        hit = rules.rule_r3("QwErTyUi")
        self.assertEqual(hit["seq"], "QwErTyUi")
        self.assertEqual(hit["span"], [0, 8])

    def test_no_shift_layer(self):
        # 不认 Shift 符号层；~!@#$% 不算数字行
        self.assertIsNone(rules.rule_r3("~!@#"))
        # 跨列行走（1qaz2wsx）不算
        self.assertIsNone(rules.rule_r3("1qaz"))

    def test_longest_and_earliest(self):
        hit = rules.rule_r3("qwertyQWERTY")
        self.assertEqual(hit["span"], [0, 6])
        hit = rules.rule_r3("zqwertasdfg")
        self.assertEqual(hit["seq"], "qwert")  # 并列 5 取起点小
        self.assertEqual(hit["span"], [1, 6])


class TestR4(unittest.TestCase):
    def test_simple(self):
        hit = rules.rule_r4("aaaaaa")
        self.assertEqual((hit["unit"], hit["repeat"]), ("a", 6))
        hit = rules.rule_r4("abcabcabc")
        self.assertEqual((hit["unit"], hit["repeat"]), ("abc", 3))

    def test_minimal_m(self):
        hit = rules.rule_r4("ababab")
        self.assertEqual((hit["unit"], hit["repeat"]), ("ab", 3))

    def test_unicode_unit(self):
        hit = rules.rule_r4("密码密码密码密码")
        self.assertEqual((hit["unit"], hit["repeat"]), ("密码", 4))

    def test_trimmed_candidate(self):
        hit = rules.rule_r4("1aaaa1")
        self.assertEqual((hit["unit"], hit["repeat"], hit["span"]), ("a", 4, [1, 5]))
        # 全是 D/S：trim 为空，仍看原串
        hit = rules.rule_r4("!!!!!!!!")
        self.assertEqual((hit["unit"], hit["repeat"], hit["span"]), ("!", 8, [0, 8]))

    def test_repeat_boundary(self):
        self.assertIsNone(rules.rule_r4("abab"))      # 只重复 2 次
        hit = rules.rule_r4("aaa")                    # m=1 重复 3 次，命中
        self.assertEqual((hit["unit"], hit["repeat"]), ("a", 3))
        self.assertIsNone(rules.rule_r4("abcabcab"))  # 长度不是 m 倍数
        self.assertIsNone(rules.rule_r4("aabbccdd"))


class TestR5(unittest.TestCase):
    def check(self, password, username="", email=""):
        return rules.rule_r5(password, username, email)

    def test_exact_reject(self):
        hit = self.check("zhang.wei", username="zhang.wei")
        self.assertEqual(hit["level"], "拒")
        self.assertEqual(hit["cand"], "username")
        self.assertEqual((hit["dist"], hit["max_len"]), (0, 9))
        self.assertIsNone(hit["span"])

    def test_threshold_reject(self):
        # dist=1, max_len=9 -> 5<=9 拒
        hit = self.check("zhang-wei", username="zhang.wei")
        self.assertEqual(hit["level"], "拒")

    def test_threshold_penalty(self):
        # zhang.wei2024 vs zhang.wei: dist=4, max_len=13, 20>13, 20<=26 扣
        hit = self.check("zhang.wei2024", username="zhang.wei")
        self.assertEqual(hit["level"], "扣")

    def test_no_entry(self):
        self.assertIsNone(self.check("lina2024", username="lina",
                                     email="li.na@corp.example.net"))

    def test_candidate_order_and_labels(self):
        hit = self.check("li.na", username="lina",
                         email="li.na@corp.example.net")
        self.assertEqual(hit["cand"], "email-local")
        hit = self.check("name@x", username="name@x")
        self.assertEqual(hit["cand"], "username")
        # 完整邮箱候选也参与
        hit = self.check("li.na@corp.example.net", username="",
                         email="li.na@corp.example.net")
        self.assertEqual(hit["cand"], "email")

    def test_case_folded(self):
        hit = self.check("Zhang.Wei", username="zhang.wei")
        self.assertEqual((hit["dist"], hit["level"]), (0, "拒"))

    def test_tie_keeps_earlier(self):
        # 与 username、email-local 距离并列时取序前的 username
        hit = self.check("abc", username="abc", email="abc@x.com")
        self.assertEqual(hit["cand"], "username")

    def test_empty(self):
        self.assertIsNone(self.check("anything", username="", email=""))


class TestLevenshtein(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(rules.levenshtein("", ""), 0)
        self.assertEqual(rules.levenshtein("abc", ""), 3)
        self.assertEqual(rules.levenshtein("", "abc"), 3)
        self.assertEqual(rules.levenshtein("abc", "abc"), 0)
        self.assertEqual(rules.levenshtein("kitten", "sitting"), 3)

    def test_fuzz(self):
        rng = random.Random(20241002)
        alphabet = "abc1@. -"
        for _ in range(3000):
            a = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 12)))
            b = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 12)))
            self.assertEqual(
                rules.levenshtein(a, b), naive_levenshtein(a, b), (a, b)
            )


class TestEvaluate(unittest.TestCase):
    def test_passed_and_score(self):
        passed, score, entries = rules.evaluate(
            "zq7&km2#vt9!", "ops-team", "ops@example.com", lambda k: None
        )
        self.assertEqual(score, 66)
        self.assertFalse(passed)  # 分数不够

        passed, score, entries = rules.evaluate(
            "Zq7&Km2#Vt9!Rs4", "ops-team", "ops@example.com", lambda k: None
        )
        self.assertEqual(score, 87)
        self.assertTrue(passed)

    def test_penalty_applied(self):
        passed, score, _ = rules.evaluate(
            "zhang.wei2024", "zhang.wei", "zhang.wei@example.com", lambda k: None
        )
        self.assertEqual(score, 50)  # base 70 - 20
        self.assertFalse(passed)

    def test_veto_beats_high_score(self):
        passed, score, entries = rules.evaluate(
            "sunshine2024!", "ops-team", "ops@example.com",
            {"sunshine": "sunshine"}.get,
        )
        self.assertEqual(score, 70)
        self.assertFalse(passed)

    def test_r1_always_first(self):
        _, _, entries = rules.evaluate(
            "qwerty", "x", "x@y.z", {"qwerty": "qwerty"}.get
        )
        self.assertEqual([e["rule"] for e in entries[:1]], ["R1"])


if __name__ == "__main__":
    unittest.main()
