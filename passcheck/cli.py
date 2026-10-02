"""命令行入口：evaluate / report。"""

import argparse
import json
import os
import sqlite3
import sys
import tempfile

from . import report as report_mod
from . import rules
from .wordlist import InputError, open_index

VAR_DIR = "var"


def _list_case_files(cases_dir):
    try:
        entries = os.listdir(cases_dir)
    except OSError as exc:
        raise InputError("用例目录不可读: %s (%s)" % (cases_dir, exc))
    names = sorted(
        name for name in entries
        if name.endswith(".jsonl")
        and os.path.isfile(os.path.join(cases_dir, name))
    )
    if not names:
        raise InputError("用例目录里没有 .jsonl 文件: %s" % cases_dir)
    return [os.path.join(cases_dir, name) for name in names]


def _iter_raw_cases(paths):
    for path in paths:
        try:
            fh = open(path, "r", encoding="utf-8", newline="")
        except OSError as exc:
            raise InputError("用例文件不可读: %s (%s)" % (path, exc))
        with fh:
            for lineno, line in enumerate(fh, 1):
                try:
                    obj = json.loads(line)
                except ValueError:
                    raise InputError(
                        "用例解析失败: %s 第 %d 行" % (path, lineno)
                    )
                if not isinstance(obj, dict):
                    raise InputError("用例不是对象: %s 第 %d 行" % (path, lineno))
                for field in ("id", "password", "username", "email"):
                    if field not in obj or not isinstance(obj[field], str):
                        raise InputError(
                            "用例字段缺失或类型不对: %s 第 %d 行 (%s)"
                            % (path, lineno, field)
                        )
                yield obj


def _result_line(record):
    return json.dumps(
        record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + "\n"


class _IdSet:
    """用 sqlite 落盘做 id 去重，避免把全部 id 堆进内存。"""

    def __init__(self, var_dir):
        fd, self._path = tempfile.mkstemp(prefix="ids-", suffix=".sqlite3", dir=var_dir)
        os.close(fd)
        self._conn = sqlite3.connect(self._path)
        self._conn.execute("PRAGMA journal_mode=OFF")
        self._conn.execute("PRAGMA synchronous=OFF")
        self._conn.execute("CREATE TABLE ids (id TEXT PRIMARY KEY) WITHOUT ROWID")

    def add(self, case_id, where):
        try:
            self._conn.execute("INSERT INTO ids (id) VALUES (?)", (case_id,))
        except sqlite3.IntegrityError:
            raise InputError("用例 id 重复: %s (%s)" % (case_id, where))

    def close(self):
        self._conn.close()
        try:
            os.remove(self._path)
        except OSError:
            pass


def _evaluate_to_file(wordlists_dir, cases_dir, out_path):
    """评估全部用例并写结果到 out_path（先写临时文件，成功后替换）。"""
    os.makedirs(VAR_DIR, exist_ok=True)
    index = open_index(wordlists_dir, VAR_DIR)
    ids = _IdSet(VAR_DIR)
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".results-", suffix=".tmp", dir=out_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            for path in _list_case_files(cases_dir):
                for obj in _iter_raw_cases([path]):
                    ids.add(obj["id"], "%s (%s)" % (obj["id"], path))
                    passed, score, rule_entries = rules.evaluate(
                        obj["password"], obj["username"], obj["email"],
                        index.lookup,
                    )
                    out.write(_result_line({
                        "id": obj["id"],
                        "passed": passed,
                        "score": score,
                        "rules": rule_entries,
                    }))
        os.replace(tmp_path, out_path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    finally:
        ids.close()
        index.close()


def _cmd_evaluate(args):
    if args.out is None:
        fd, tmp_path = tempfile.mkstemp(prefix=".results-", suffix=".tmp", dir=VAR_DIR if os.path.isdir(VAR_DIR) else None)
        os.close(fd)
        try:
            _evaluate_to_file(args.wordlists, args.cases, tmp_path)
            with open(tmp_path, "r", encoding="utf-8", newline="") as fh:
                for chunk in iter(lambda: fh.read(1 << 16), ""):
                    sys.stdout.write(chunk)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    else:
        _evaluate_to_file(args.wordlists, args.cases, args.out)
    return 0


def _cmd_report(args):
    os.makedirs(VAR_DIR, exist_ok=True)
    fd, results_path = tempfile.mkstemp(prefix=".results-", suffix=".jsonl", dir=VAR_DIR)
    os.close(fd)
    try:
        _evaluate_to_file(args.wordlists, args.cases, results_path)

        def results_iter():
            with open(results_path, "r", encoding="utf-8", newline="") as fh:
                for line in fh:
                    yield json.loads(line)

        html_dir = os.path.dirname(os.path.abspath(args.html))
        os.makedirs(html_dir, exist_ok=True)
        fd, tmp_html = tempfile.mkstemp(prefix=".report-", suffix=".tmp", dir=html_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
                report_mod.write_report(results_iter, out)
            os.replace(tmp_html, args.html)
        except BaseException:
            try:
                os.remove(tmp_html)
            except OSError:
                pass
            raise
    finally:
        try:
            os.remove(results_path)
        except OSError:
            pass
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="passcheck", description="口令强度评估"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("evaluate", "批量评估并输出 JSONL"),
                            ("report", "评估并生成自包含 HTML 报告")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--wordlists", required=True, help="词表目录")
        p.add_argument("--cases", required=True, help="用例目录")
        if name == "evaluate":
            p.add_argument("--out", default=None, help="结果文件（省略写 stdout）")
        else:
            p.add_argument("--html", required=True, help="报告输出路径")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "evaluate":
            return _cmd_evaluate(args)
        return _cmd_report(args)
    except InputError as exc:
        print("passcheck: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
