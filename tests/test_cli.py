"""CLI 端到端测试：退出码、stdout、错误不写输出、确定性、报告结构。"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WORDLISTS = "\n".join([
    "password",
    "Password1!",
    "monkey",
    "factory",
    "qwerty123",
    "1234",
    "# comment",
    "",
]) + "\n"

CASES = [
    {"id": "t-001", "password": "Zq7&Km2#Vt9!", "username": "u", "email": "u@e.com"},
    {"id": "t-002", "password": "Password1!", "username": "u", "email": "u@e.com"},
    {"id": "t-003", "password": "zhang.wei2024", "username": "zhang.wei",
     "email": "zhang.wei@example.com"},
    {"id": "t-004", "password": "1aaaa1", "username": "u", "email": "u@e.com"},
]


def line(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.wdir = os.path.join(self.dir, "wordlists")
        self.cdir = os.path.join(self.dir, "cases")
        os.makedirs(self.wdir)
        os.makedirs(self.cdir)
        with open(os.path.join(self.wdir, "w.txt"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write(WORDLISTS)
        with open(os.path.join(self.cdir, "c-01.jsonl"), "w", encoding="utf-8",
                  newline="\n") as fh:
            for case in CASES:
                fh.write(line(case))

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *extra, cwd=None, env_seed=None):
        env = dict(os.environ)
        env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")
        if env_seed is not None:
            env["PYTHONHASHSEED"] = str(env_seed)
        proc = subprocess.run(
            [sys.executable, "-m", "passcheck", *extra],
            cwd=cwd or self.dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return proc

    def test_evaluate_out(self):
        proc = self.run_cli(
            "evaluate", "--wordlists", "wordlists", "--cases", "cases",
            "--out", "results.jsonl",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = [json.loads(x) for x in
                open(os.path.join(self.dir, "results.jsonl"), encoding="utf-8")]
        self.assertEqual(len(rows), len(CASES))
        self.assertTrue(rows[0]["passed"])
        self.assertFalse(rows[1]["passed"])
        self.assertEqual(rows[1]["rules"][1]["term"], "Password1!")
        self.assertEqual(rows[2]["score"], 50)
        self.assertEqual(rows[3]["rules"][1]["span"], [1, 5])

    def test_stdout(self):
        proc = self.run_cli(
            "evaluate", "--wordlists", "wordlists", "--cases", "cases",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.count("\n"), len(CASES))

    def test_usage_error_is_code_2(self):
        proc = self.run_cli("evaluate", "--cases", "cases")
        self.assertEqual(proc.returncode, 2)

    def test_missing_wordlists_code_1_no_output(self):
        proc = self.run_cli(
            "evaluate", "--wordlists", "nope", "--cases", "cases",
            "--out", "out.jsonl",
        )
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "out.jsonl")))

    def test_parse_error_code_1_no_output(self):
        with open(os.path.join(self.cdir, "c-02.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("{not json\n")
        proc = self.run_cli(
            "evaluate", "--wordlists", "wordlists", "--cases", "cases",
            "--out", "out.jsonl",
        )
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "out.jsonl")))

    def test_duplicate_id_code_1(self):
        with open(os.path.join(self.cdir, "c-02.jsonl"), "w", encoding="utf-8",
                  newline="\n") as fh:
            dup = dict(CASES[0])
            fh.write(line(dup))
        proc = self.run_cli(
            "evaluate", "--wordlists", "wordlists", "--cases", "cases",
            "--out", "out.jsonl",
        )
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "out.jsonl")))

    def test_missing_field_code_1(self):
        with open(os.path.join(self.cdir, "c-02.jsonl"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write(line({"id": "x", "password": "a", "username": "u"}))
        proc = self.run_cli(
            "evaluate", "--wordlists", "wordlists", "--cases", "cases",
            "--out", "out.jsonl",
        )
        self.assertEqual(proc.returncode, 1)

    def test_determinism_and_hashseed(self):
        outputs = []
        for seed in (0, 12345):
            proc = self.run_cli(
                "evaluate", "--wordlists", "wordlists", "--cases", "cases",
                "--out", "r%d.jsonl" % seed, env_seed=seed,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            outputs.append(open(os.path.join(self.dir, "r%d.jsonl" % seed),
                                encoding="utf-8").read())
        self.assertEqual(outputs[0], outputs[1])

    def test_report_tables_match_results(self):
        proc = self.run_cli(
            "report", "--wordlists", "wordlists", "--cases", "cases",
            "--html", "report.html",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(os.path.join(self.dir, "report.html"), encoding="utf-8") as fh:
            html_text = fh.read()
        self.assertNotIn("<script", html_text.lower())

        results = [json.loads(x) for x in subprocess.run(
            [sys.executable, "-m", "passcheck", "evaluate",
             "--wordlists", "wordlists", "--cases", "cases"],
            cwd=self.dir, env={**os.environ, "PYTHONPATH": REPO_ROOT},
            stdout=subprocess.PIPE, text=True).stdout.splitlines()]

        bands = {}
        rejected = []

        class Parser(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag != "tr":
                    return
                d = dict(attrs)
                if "data-band" in d:
                    bands[d["data-band"]] = int(d["data-count"])
                if "data-id" in d:
                    rejected.append((d["data-id"], int(d["data-score"]),
                                     d["data-rules"]))

        Parser().feed(html_text)
        labels = ["0-9", "10-19", "20-29", "30-39", "40-49",
                  "50-59", "60-69", "70-79", "80-89", "90-100"]
        self.assertEqual(list(bands), labels)
        counts = [0] * 10
        expected_rejected = []
        for r in results:
            counts[min(r["score"] // 10, 9)] += 1
            if not r["passed"]:
                parts = []
                for e in r["rules"]:
                    span = e["span"]
                    parts.append("%s@-" % e["rule"] if span is None
                                 else "%s@%d-%d" % (e["rule"], span[0], span[1]))
                expected_rejected.append((r["id"], r["score"], ";".join(parts)))
        self.assertEqual([bands[l] for l in labels], counts)
        self.assertEqual(rejected, expected_rejected)


if __name__ == "__main__":
    unittest.main()
