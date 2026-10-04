"""样例验收：samples/cases 全量评估，与 samples/expected 逐字节一致。"""

import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(REPO_ROOT, "samples")


@unittest.skipUnless(os.path.isdir(SAMPLES), "samples/ 不存在")
class TestSamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.results = os.path.join(cls.tmp.name, "results.jsonl")
        env = dict(os.environ)
        env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-m", "passcheck", "evaluate",
             "--wordlists", os.path.join(SAMPLES, "wordlists"),
             "--cases", os.path.join(SAMPLES, "cases"),
             "--out", cls.results],
            cwd=cls.tmp.name, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError("evaluate 失败: %s" % proc.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_results_match_expected_byte_for_byte(self):
        expected_dir = os.path.join(SAMPLES, "expected")
        names = sorted(n for n in os.listdir(expected_dir) if n.endswith(".jsonl"))
        with open(self.results, "rb") as fh:
            actual = fh.read()
        chunks = []
        for name in names:
            with open(os.path.join(expected_dir, name), "rb") as fh:
                chunks.append(fh.read())
        self.assertEqual(actual, b"".join(chunks))

    def test_report_matches_results(self):
        from html.parser import HTMLParser
        import json

        html_path = os.path.join(self.tmp.name, "strength.html")
        env = dict(os.environ)
        env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-m", "passcheck", "report",
             "--wordlists", os.path.join(SAMPLES, "wordlists"),
             "--cases", os.path.join(SAMPLES, "cases"),
             "--html", html_path],
            cwd=self.tmp.name, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(html_path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("<script", text.lower())

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

        Parser().feed(text)
        labels = ["0-9", "10-19", "20-29", "30-39", "40-49",
                  "50-59", "60-69", "70-79", "80-89", "90-100"]
        self.assertEqual(list(bands), labels)
        counts = [0] * 10
        expected_rejected = []
        with open(self.results, encoding="utf-8") as fh:
            for raw in fh:
                r = json.loads(raw)
                counts[min(r["score"] // 10, 9)] += 1
                if not r["passed"]:
                    parts = []
                    for e in r["rules"]:
                        span = e["span"]
                        parts.append(
                            "%s@-" % e["rule"] if span is None
                            else "%s@%d-%d" % (e["rule"], span[0], span[1])
                        )
                    expected_rejected.append((r["id"], r["score"], ";".join(parts)))
        self.assertEqual([bands[l] for l in labels], counts)
        self.assertEqual(rejected, expected_rejected)


if __name__ == "__main__":
    unittest.main()
