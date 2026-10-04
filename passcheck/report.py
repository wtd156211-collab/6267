"""自包含 HTML 报告：评分分布 + 被拒清单，数字全部来自引擎结果。"""

import html

BAND_LABELS = (
    "0-9", "10-19", "20-29", "30-39", "40-49",
    "50-59", "60-69", "70-79", "80-89", "90-100",
)

_HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>口令强度评估报告</title>
<style>
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:2em;color:#222}
h1{font-size:1.4em}
table{border-collapse:collapse;margin:1.2em 0;min-width:26em}
caption{font-weight:600;text-align:left;margin-bottom:.4em}
th,td{border:1px solid #c9c9c9;padding:.3em .8em;text-align:left;font-size:.92em}
th{background:#f2f2f2}
tbody tr:nth-child(even){background:#fafafa}
td.num{text-align:right;font-variant-numeric:tabular-nums}
</style>
</head>
<body>
<h1>口令强度评估报告</h1>
"""

_TAIL = """</body>
</html>
"""


def rules_attr(rules):
    """rules 按序写成 `规则号@起-止`，R5 无片段写 `R5@-`，`;` 连接。"""
    parts = []
    for entry in rules:
        span = entry["span"]
        if span is None:
            parts.append("%s@-" % entry["rule"])
        else:
            parts.append("%s@%d-%d" % (entry["rule"], span[0], span[1]))
    return ";".join(parts)


def rejected_row(case_id, result):
    """一条被拒样本的 <tr> 片段。"""
    rid = html.escape(case_id, quote=True)
    rattr = html.escape(rules_attr(result["rules"]), quote=True)
    score = result["score"]
    return (
        '<tr data-id="%s" data-score="%d" data-rules="%s">'
        "<td>%s</td><td class=\"num\">%d</td><td>%s</td></tr>\n"
        % (rid, score, rattr, rid, score, rattr)
    )


def write_head(out, total, passed):
    out.write(_HEAD)
    out.write(
        "<p>共 %d 条样本：通过 %d 条，拒绝 %d 条。评分、结论与拦截依据均来自评估引擎。</p>\n"
        % (total, passed, total - passed)
    )


def write_bands(out, bands):
    out.write('<table id="bands">\n')
    out.write("<caption>评分分布</caption>\n")
    out.write("<thead><tr><th>分数段</th><th>数量</th></tr></thead>\n")
    out.write("<tbody>\n")
    for label, count in zip(BAND_LABELS, bands):
        out.write(
            '<tr data-band="%s" data-count="%d"><td>%s</td><td class="num">%d</td></tr>\n'
            % (label, count, label, count)
        )
    out.write("</tbody>\n</table>\n")


def write_rejected_head(out):
    out.write('<table id="rejected">\n')
    out.write("<caption>被拒样本（行序同评估结果）</caption>\n")
    out.write(
        "<thead><tr><th>id</th><th>score</th><th>rules</th></tr></thead>\n"
    )
    out.write("<tbody>\n")


def write_tail(out):
    out.write("</tbody>\n</table>\n")
    out.write(_TAIL)
