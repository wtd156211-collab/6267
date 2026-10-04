"""命令行入口：evaluate / report。"""

import argparse
import json
import os
import shutil
import sys

from .engine import evaluate_password
from .report import (
    rejected_row,
    write_bands,
    write_head,
    write_rejected_head,
    write_tail,
)
from .wordlist import WordlistError, WordlistIndex, list_wordlists

INDEX_PATH = os.path.join("var", "wordlist-index.sqlite3")
VAR_DIR = "var"


class InputError(Exception):
    """输入不可用（退出码 1）。"""


def _iter_case_files(cases_dir):
    if not os.path.isdir(cases_dir):
        raise InputError("用例目录不可用: %s" % cases_dir)
    names = sorted(
        name for name in os.listdir(cases_dir)
        if name.endswith(".jsonl")
        and os.path.isfile(os.path.join(cases_dir, name))
    )
    if not names:
        raise InputError("用例目录下没有 .jsonl 文件: %s" % cases_dir)
    return [os.path.join(cases_dir, name) for name in names]


def _iter_cases(files):
    """逐行产出 (id, password, username, email)，附带输入校验。"""
    seen_ids = set()
    for path in files:
        try:
            fh = open(path, encoding="utf-8")
        except OSError as exc:
            raise InputError("用例文件不可读: %s (%s)" % (path, exc)) from exc
        with fh:
            for lineno, line in enumerate(fh, 1):
                where = "%s:%d" % (path, lineno)
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise InputError("用例解析失败: %s (%s)" % (where, exc)) from exc
                if not isinstance(record, dict):
                    raise InputError("用例不是对象: %s" % where)
                try:
                    case_id = record["id"]
                    password = record["password"]
                    username = record["username"]
                    email = record["email"]
                except KeyError as exc:
                    raise InputError("用例字段缺失: %s (%s)" % (where, exc)) from exc
                for field, value in (
                    ("id", case_id),
                    ("password", password),
                    ("username", username),
                    ("email", email),
                ):
                    if not isinstance(value, str):
                        raise InputError(
                            "用例字段类型错误: %s (%s)" % (where, field)
                        )
                if case_id in seen_ids:
                    raise InputError("用例 id 重复: %s (%s)" % (where, case_id))
                seen_ids.add(case_id)
                yield case_id, password, username, email


def _result_line(case_id, result):
    record = {
        "id": case_id,
        "passed": result["passed"],
        "score": result["score"],
        "rules": result["rules"],
    }
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _open_index(wordlists_dir):
    try:
        wordlists = list_wordlists(wordlists_dir)
    except WordlistError as exc:
        raise InputError(str(exc)) from exc
    try:
        index = WordlistIndex(INDEX_PATH)
        index.open(wordlists)
    except (OSError, UnicodeDecodeError, WordlistError) as exc:
        raise InputError("词表不可用: %s (%s)" % (wordlists_dir, exc)) from exc
    return index


def _cmd_evaluate(args):
    files = _iter_case_files(args.cases)
    index = _open_index(args.wordlists)
    try:
        if args.out:
            tmp_path = args.out + ".tmp"
        else:
            os.makedirs(VAR_DIR, exist_ok=True)
            tmp_path = os.path.join(VAR_DIR, "evaluate.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8", newline="\n") as out:
                for case_id, password, username, email in _iter_cases(files):
                    result = evaluate_password(
                        password, username, email, index.lookup
                    )
                    out.write(_result_line(case_id, result))
                    out.write("\n")
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
        if args.out:
            os.replace(tmp_path, args.out)
        else:
            with open(tmp_path, "rb") as fh:
                shutil.copyfileobj(fh, sys.stdout.buffer)
            os.remove(tmp_path)
    finally:
        index.close()
    return 0


def _cmd_report(args):
    files = _iter_case_files(args.cases)
    index = _open_index(args.wordlists)
    os.makedirs(VAR_DIR, exist_ok=True)
    frag_path = os.path.join(VAR_DIR, "rejected.frag.tmp")
    tmp_html = args.html + ".tmp"
    try:
        bands = [0] * 10
        total = 0
        passed = 0
        try:
            with open(frag_path, "w", encoding="utf-8", newline="\n") as frag:
                for case_id, password, username, email in _iter_cases(files):
                    result = evaluate_password(
                        password, username, email, index.lookup
                    )
                    bands[min(result["score"] // 10, 9)] += 1
                    total += 1
                    if result["passed"]:
                        passed += 1
                    else:
                        frag.write(rejected_row(case_id, result))
        except BaseException:
            if os.path.exists(frag_path):
                os.remove(frag_path)
            raise
        try:
            with open(tmp_html, "w", encoding="utf-8", newline="\n") as out:
                write_head(out, total, passed)
                write_bands(out, bands)
                write_rejected_head(out)
                with open(frag_path, encoding="utf-8", newline="") as frag:
                    shutil.copyfileobj(frag, out)
                write_tail(out)
        except BaseException:
            if os.path.exists(tmp_html):
                os.remove(tmp_html)
            raise
        os.replace(tmp_html, args.html)
        os.remove(frag_path)
    finally:
        index.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="passcheck", description="口令强度评估"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_eval = sub.add_parser("evaluate", help="批量评估，输出 JSONL")
    p_eval.add_argument("--wordlists", required=True)
    p_eval.add_argument("--cases", required=True)
    p_eval.add_argument("--out", default=None)
    p_eval.set_defaults(func=_cmd_evaluate)

    p_report = sub.add_parser("report", help="批量评估并生成 HTML 报告")
    p_report.add_argument("--wordlists", required=True)
    p_report.add_argument("--cases", required=True)
    p_report.add_argument("--html", required=True)
    p_report.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (InputError, WordlistError, OSError) as exc:
        print("passcheck: %s" % exc, file=sys.stderr)
        return 1
