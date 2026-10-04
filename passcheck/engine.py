"""评估引擎：组合 R1–R5，产出 score / passed / rules。"""

from .rules import (
    base_score,
    fold,
    keyboard_run,
    repeat_unit,
    trim_bounds,
    user_similarity,
)


def _lower_with_map(password):
    """返回 (小写折叠串, 下标映射)。

    下标映射把折叠串的每个码点位置映回原口令位置；长度不变时为 None
    （恒等映射的快路径）。str.lower() 逐码点独立，映射安全。
    """
    low = password.lower()
    if len(low) == len(password):
        return low, None
    parts = []
    pos = []
    for i, ch in enumerate(password):
        lowered = ch.lower()
        parts.append(lowered)
        pos.extend([i] * len(lowered))
    return "".join(parts), pos


def _span(pos, start, end):
    """low 串上的 [start, end) 映回原口令区间。"""
    if pos is None:
        return start, end
    return pos[start], pos[end - 1] + 1


def evaluate_password(password, username, email, lookup):
    """评估一条口令。

    lookup(keys) -> {key: term}，精确词表查询（R2）。
    返回 {"passed": bool, "score": int, "rules": [...]}。
    """
    n = len(password)
    base = base_score(password)
    rules = [{"rule": "R1", "base": base, "span": [0, n]}]
    veto = False

    low, pos = _lower_with_map(password)
    lead, trail = trim_bounds(low)
    trimmed = low[lead:len(low) - trail]
    trim_span = _span(pos, lead, len(low) - trail) if trimmed else None

    # R2 常见口令：查表键按序，空键跳过，命中第一个即停。
    keys = []
    seen = set()

    def add_key(variant, key, span):
        if key and key not in seen:
            seen.add(key)
            keys.append((variant, key, span))

    add_key("原样", low, (0, n))
    add_key("去前后缀", trimmed, trim_span)
    add_key("形近替换", fold(low), (0, n))
    add_key("去前后缀+形近替换", fold(trimmed), trim_span)

    hits = lookup([key for _, key, _ in keys])
    for variant, key, span in keys:
        term = hits.get(key)
        if term is not None:
            rules.append({
                "rule": "R2",
                "term": term,
                "variant": variant,
                "span": [span[0], span[1]],
            })
            veto = True
            break

    # R3 键盘序列。
    run = keyboard_run(low)
    if run is not None:
        start, end = _span(pos, run[0], run[1])
        rules.append({
            "rule": "R3",
            "seq": password[start:end],
            "span": [start, end],
        })
        veto = True

    # R4 重复模式：口令本身，再 trim(口令)（非空且不同才看）。
    hit = repeat_unit(password)
    if hit is not None:
        unit, repeat = hit
        rules.append({
            "rule": "R4",
            "unit": unit,
            "repeat": repeat,
            "span": [0, n],
        })
        veto = True
    else:
        lead2, trail2 = trim_bounds(password)
        core = password[lead2:n - trail2]
        if core and (lead2 or trail2):
            hit = repeat_unit(core)
            if hit is not None:
                unit, repeat = hit
                rules.append({
                    "rule": "R4",
                    "unit": unit,
                    "repeat": repeat,
                    "span": [lead2, n - trail2],
                })
                veto = True

    # R5 与用户信息相似度。
    deduct = False
    r5 = user_similarity(low, username, email)
    if r5 is not None:
        rules.append(r5)
        if r5["level"] == "拒":
            veto = True
        else:
            deduct = True

    score = max(0, base - (20 if deduct else 0))
    return {
        "passed": score >= 70 and not veto,
        "score": score,
        "rules": rules,
    }
