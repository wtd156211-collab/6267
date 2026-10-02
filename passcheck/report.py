"""自包含 HTML 报告：数据全部来自引擎产出的结果行，不另算。"""

import html

BAND_LABELS = [
    "0-9", "10-19", "20-29", "30-39", "40-49",
    "50-59", "60-69", "70-79", "80-89", "90-100",
]

_CSS = """
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:2em;color:#222}
h1{font-size:1.4em}h2{font-size:1.1em;margin-top:1.6em}
table{border-collapse:collapse;margin-top:.6em}
th,td{border:1px solid #ccc;padding:.3em .8em;text-align:left;font-size:.92em}
th{background:#f0f0f0}
td.num,th.num{text-align:right}
.mono{font-family:ui-monospace,Consolas,monospace}
tr.rejected td{background:#fff5f5}
"""


def band_index(score):
    return min(score // 10, 9)


def rule_tag(entry):
    """data-rules 里的单条：规则号@起-止；R5 无片段写 R5@-。"""
    span = entry.get("span")
    if span is None:
        return "%s@-" % entry["rule"]
    return "%s@%d-%d" % (entry["rule"], span[0], span[1])


def rule_detail(entry):
    """给人看的拦截依据明细。"""
    rule = entry["rule"]
    span = entry.get("span")
    where = "" if span is None else " [%d,%d)" % (span[0], span[1])
    if rule == "R1":
        return "R1 基准分 %d%s" % (entry["base"], where)
    if rule == "R2":
        return "R2 命中常见口令 %s（%s）%s" % (
            html.escape(entry["term"]), html.escape(entry["variant"]), where,
        )
    if rule == "R3":
        return "R3 键盘序列 %s%s" % (html.escape(entry["seq"]), where)
    if rule == "R4":
        return "R4 重复模式 %s ×%d%s" % (
            html.escape(entry["unit"]), entry["repeat"], where,
        )
    if rule == "R5":
        return "R5 与用户信息相似（%s）%s dist=%d max_len=%d" % (
            html.escape(entry["level"]), html.escape(entry["cand"]),
            entry["dist"], entry["max_len"],
        )
    return rule


def write_report(results_iter, out):
    """results_iter 产出结果行 dict（引擎输出）；out 是可写文本流。

    需要遍历两遍：第一遍统计分档，第二遍写被拒清单。
    调用方传入可重入的迭代器工厂。
    """
    counts = [0] * 10
    total = 0
    rejected = 0
    for record in results_iter():
        counts[band_index(record["score"])] += 1
        total += 1
        if not record["passed"]:
            rejected += 1

    esc = html.escape
    write = out.write
    write("<!DOCTYPE html>\n")
    write('<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n')
    write("<title>口令强度评估报告</title>\n")
    write("<style>%s</style>\n" % _CSS)
    write("</head>\n<body>\n")
    write("<h1>口令强度评估报告</h1>\n")
    write("<p>共 %d 条用例：通过 %d 条，拒绝 %d 条。</p>\n" % (total, total - rejected, rejected))

    write("<h2>评分分布</h2>\n")
    write('<table id="bands">\n')
    write("<thead><tr><th>分数段</th><th class=\"num\">数量</th></tr></thead>\n<tbody>\n")
    for label, count in zip(BAND_LABELS, counts):
        write(
            '<tr data-band="%s" data-count="%d"><td>%s</td><td class="num">%d</td></tr>\n'
            % (label, count, label, count)
        )
    write("</tbody>\n</table>\n")

    write("<h2>被拒样本</h2>\n")
    write('<table id="rejected">\n')
    write(
        "<thead><tr><th>ID</th><th class=\"num\">分数</th>"
        "<th>拦截依据</th></tr></thead>\n<tbody>\n"
    )
    for record in results_iter():
        if record["passed"]:
            continue
        rules = record["rules"]
        tags = ";".join(rule_tag(entry) for entry in rules)
        details = "；".join(rule_detail(entry) for entry in rules)
        write(
            '<tr class="rejected" data-id="%s" data-score="%d" data-rules="%s">'
            '<td class="mono">%s</td><td class="num">%d</td><td>%s</td></tr>\n'
            % (
                esc(record["id"], quote=True), record["score"],
                esc(tags, quote=True),
                esc(record["id"]), record["score"], details,
            )
        )
    write("</tbody>\n</table>\n")
    write("</body>\n</html>\n")
