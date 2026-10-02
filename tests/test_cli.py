import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(REPO, "samples")


def run_cli(args, cwd):
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "passcheck"] + args,
        cwd=cwd, env=env, capture_output=True, text=True,
    )


class CliBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def evaluate(self, cases_dir, extra=()):
        out = os.path.join(self.dir, "results.jsonl")
        proc = run_cli(
            ["evaluate", "--wordlists", os.path.join(SAMPLES, "wordlists"),
             "--cases", cases_dir, "--out", out] + list(extra),
            cwd=self.dir,
        )
        return proc, out


class TestCliSmall(CliBase):
    """小用例集（c-01..c-06）端到端，对照 samples/expected。"""

    def setUp(self):
        super().setUp()
        self.cases = os.path.join(self.dir, "cases")
        os.makedirs(self.cases)
        self.expected = []
        for name in sorted(os.listdir(os.path.join(SAMPLES, "cases"))):
            if name.startswith("c-07"):
                continue
            shutil.copy(os.path.join(SAMPLES, "cases", name),
                        os.path.join(self.cases, name))
            with open(os.path.join(SAMPLES, "expected", name),
                      encoding="utf-8") as fh:
                self.expected.append(fh.read())

    def test_results_match_expected(self):
        proc, out = self.evaluate(self.cases)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(out, encoding="utf-8") as fh:
            got = fh.read()
        self.assertEqual(got, "".join(self.expected))

    def test_stdout_when_no_out(self):
        proc = run_cli(
            ["evaluate", "--wordlists", os.path.join(SAMPLES, "wordlists"),
             "--cases", self.cases],
            cwd=self.dir,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "".join(self.expected))

    def test_deterministic_across_hash_seed(self):
        proc, out = self.evaluate(self.cases)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(out, "rb") as fh:
            first = fh.read()
        env = dict(os.environ)
        env["PYTHONPATH"] = REPO
        env["PYTHONHASHSEED"] = "7"
        out2 = os.path.join(self.dir, "r2.jsonl")
        proc2 = subprocess.run(
            [sys.executable, "-m", "passcheck", "evaluate",
             "--wordlists", os.path.join(SAMPLES, "wordlists"),
             "--cases", self.cases, "--out", out2],
            cwd=self.dir, env=env, capture_output=True,
        )
        self.assertEqual(proc2.returncode, 0, proc2.stderr)
        with open(out2, "rb") as fh:
            self.assertEqual(first, fh.read())


class TestCliErrors(CliBase):
    def _write_cases(self, lines):
        cases = os.path.join(self.dir, "cases")
        os.makedirs(cases, exist_ok=True)
        with open(os.path.join(cases, "c-01-x.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(lines)
        return cases

    def test_missing_dir_exit_1(self):
        proc, out = self.evaluate(os.path.join(self.dir, "nope"))
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.exists(out))

    def test_bad_json_exit_1(self):
        cases = self._write_cases("{not json}\n")
        proc, out = self.evaluate(cases)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.exists(out))

    def test_missing_field_exit_1(self):
        cases = self._write_cases(
            '{"id":"c-01-x-00001","password":"a","username":"u"}\n'
        )
        proc, out = self.evaluate(cases)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.exists(out))

    def test_duplicate_id_exit_1(self):
        line = ('{"id":"c-01-x-00001","password":"a","username":"u",'
                '"email":"e@x.z"}\n')
        cases = self._write_cases(line + line)
        proc, out = self.evaluate(cases)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.exists(out))

    def test_usage_error_exit_2(self):
        proc = run_cli(["evaluate"], cwd=self.dir)
        self.assertEqual(proc.returncode, 2)
        proc = run_cli(["nope"], cwd=self.dir)
        self.assertEqual(proc.returncode, 2)


class TestCliFull(CliBase):
    """完整样例：10 万条逐字节对照 expected，并校验报告。"""

    def test_full_evaluate_and_report(self):
        cases = os.path.join(SAMPLES, "cases")
        proc, out = self.evaluate(cases)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        expected_path = os.path.join(self.dir, "expected-all.jsonl")
        with open(expected_path, "w", encoding="utf-8", newline="") as dst:
            for name in sorted(os.listdir(os.path.join(SAMPLES, "expected"))):
                with open(os.path.join(SAMPLES, "expected", name),
                          encoding="utf-8") as fh:
                    dst.write(fh.read())
        with open(out, "rb") as fh:
            got = fh.read()
        with open(expected_path, "rb") as fh:
            self.assertEqual(got, fh.read())

        html_path = os.path.join(self.dir, "strength.html")
        proc = run_cli(
            ["report", "--wordlists", os.path.join(SAMPLES, "wordlists"),
             "--cases", cases, "--html", html_path],
            cwd=self.dir,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(html_path, encoding="utf-8") as fh:
            page = fh.read()
        self.assertNotIn("<script", page)
        self.assertIn('<table id="bands">', page)
        self.assertIn('<table id="rejected">', page)
        # 分档计数与结果行一致
        import re
        from collections import Counter
        records = [json.loads(line) for line in got.decode("utf-8").splitlines()]
        counts = Counter(min(r["score"] // 10, 9) for r in records)
        bands = re.findall(r'data-band="([^"]+)" data-count="(\d+)"', page)
        self.assertEqual(len(bands), 10)
        for idx, (label, count) in enumerate(bands):
            self.assertEqual(int(count), counts[idx])
        rejected = [r for r in records if not r["passed"]]
        rows = re.findall(r'<tr class="rejected" data-id="[^"]+"', page)
        self.assertEqual(len(rows), len(rejected))


if __name__ == "__main__":
    unittest.main()
