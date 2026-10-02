"""口令强度评估规则 R1-R5（纯函数，不读时钟/随机数/网络）。"""

# --- 2.1 字符类别 -----------------------------------------------------------

def _char_class(ch):
    o = ord(ch)
    if 97 <= o <= 122:
        return "L"
    if 65 <= o <= 90:
        return "U"
    if 48 <= o <= 57:
        return "D"
    if 33 <= o <= 47 or 58 <= o <= 64 or 91 <= o <= 96 or 123 <= o <= 126:
        return "S"
    return "O"


def _is_trim_char(ch):
    # D（ASCII 数字）或 S（ASCII 符号）
    o = ord(ch)
    return 33 <= o <= 64 or 91 <= o <= 96 or 123 <= o <= 126


def trim_span(s):
    """返回去掉首尾 D/S 字符后的区间 [start, end)。"""
    start = 0
    end = len(s)
    while start < end and _is_trim_char(s[start]):
        start += 1
    while end > start and _is_trim_char(s[end - 1]):
        end -= 1
    return start, end


_FOLD_TABLE = str.maketrans({
    "@": "a", "0": "o", "1": "i", "2": "z", "3": "e", "4": "a",
    "5": "s", "6": "g", "7": "t", "8": "b", "9": "g",
    "$": "s", "!": "i", "+": "t",
})


def fold(s):
    """形近替换，逐字符。"""
    return s.translate(_FOLD_TABLE)


# --- R1 长度与字符集 --------------------------------------------------------

def rule_r1(password):
    n = len(password)
    if n < 8:
        base = 0
    else:
        classes = {_char_class(ch) for ch in password}
        base = min(100, min(n, 16) * 4 + (len(classes) - 1) * 9)
    return {"rule": "R1", "base": base, "span": [0, n]}


# --- R2 常见口令 ------------------------------------------------------------

def r2_keys(password):
    """按序生成 (key, variant, span)，空键跳过、重复键跳过。"""
    low = password.lower()
    start, end = trim_span(low)
    trimmed = low[start:end]
    folded = fold(low)
    folded_trimmed = fold(trimmed)
    candidates = [
        (low, "原样", [0, len(password)]),
        (trimmed, "去前后缀", [start, end]),
        (folded, "形近替换", [0, len(password)]),
        (folded_trimmed, "去前后缀+形近替换", [start, end]),
    ]
    seen = set()
    for key, variant, span in candidates:
        if not key or key in seen:
            continue
        seen.add(key)
        yield key, variant, span


def rule_r2(password, lookup):
    for key, variant, span in r2_keys(password):
        term = lookup(key)
        if term is not None:
            return {"rule": "R2", "term": term, "variant": variant, "span": span}
    return None


# --- R3 键盘序列 ------------------------------------------------------------

_KEYBOARD_ROWS = (
    "`1234567890-=",
    "qwertyuiop[]\\",
    "asdfghjkl;'",
    "zxcvbnm,./",
)

_KEY_POS = {}
for _row_idx, _row in enumerate(_KEYBOARD_ROWS):
    for _col_idx, _ch in enumerate(_row):
        _KEY_POS[_ch] = (_row_idx, _col_idx)


def rule_r3(password):
    low = password.lower()
    n = len(low)
    best = None  # (length, start)
    for i in range(n):
        pos_i = _KEY_POS.get(low[i])
        if pos_i is None:
            continue
        # 沿字符串向右走；列号逐位 +1（正向）或 -1（反向书写）
        for delta in (1, -1):
            length = 1
            prev = pos_i
            j = i + 1
            while j < n:
                pos_j = _KEY_POS.get(low[j])
                if pos_j is None or pos_j[0] != prev[0]:
                    break
                if pos_j[1] - prev[1] != delta:
                    break
                length += 1
                prev = pos_j
                j += 1
            if length >= 4 and (best is None or length > best[0]):
                best = (length, i)
    if best is None:
        return None
    length, start = best
    return {
        "rule": "R3",
        "seq": password[start:start + length],
        "span": [start, start + length],
    }


# --- R4 重复模式 ------------------------------------------------------------

def _repeat_hit(s):
    for m in (1, 2, 3):
        length = len(s)
        if length % m == 0 and length // m >= 3:
            unit = s[:m]
            if unit * (length // m) == s:
                return unit, length // m
    return None


def rule_r4(password):
    candidates = [(password, 0, len(password))]
    start, end = trim_span(password)
    trimmed = password[start:end]
    if trimmed and trimmed != password:
        candidates.append((trimmed, start, end))
    for s, lo, hi in candidates:
        hit = _repeat_hit(s)
        if hit is not None:
            unit, repeat = hit
            return {
                "rule": "R4",
                "unit": unit,
                "repeat": repeat,
                "span": [lo, hi],
            }
    return None


# --- R5 与用户信息相似度 ----------------------------------------------------

def levenshtein(a, b):
    """Levenshtein 编辑距离（逐码点，增删改各 1）。Myers 位并行。"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # pattern = a（较短者省位宽），text = b
    if len(a) > len(b):
        a, b = b, a
    m = len(a)
    peq = {}
    for idx, ch in enumerate(a):
        peq[ch] = peq.get(ch, 0) | (1 << idx)
    mask = (1 << m) - 1
    pv = mask
    mv = 0
    score = m
    top = 1 << (m - 1)
    for ch in b:
        eq = peq.get(ch, 0)
        xv = eq | mv
        xh = (((eq & pv) + pv) ^ pv) | eq
        ph = mv | (~(xh | pv) & mask)
        mh = pv & xh
        if ph & top:
            score += 1
        elif mh & top:
            score -= 1
        ph = ((ph << 1) | 1) & mask
        mh = (mh << 1) & mask
        pv = (mh | (~(xv | ph) & mask))
        mv = ph & xv
    return score


def _local_part(s):
    if "@" in s:
        return s.split("@", 1)[0]
    return None


def rule_r5(password, username, email):
    candidates = []
    for label, value in (
        ("username", username),
        ("username-local", _local_part(username)),
        ("email", email),
        ("email-local", _local_part(email)),
    ):
        if value:
            candidates.append((label, value.lower()))
    if not candidates:
        return None
    low = password.lower()
    best = None  # (dist, max_len, label)
    for label, cand in candidates:
        dist = levenshtein(low, cand)
        max_len = max(len(low), len(cand))
        if max_len == 0:
            dist, max_len = 0, 0
        if best is None or dist * best[1] < best[0] * max_len:
            best = (dist, max_len, label)
    dist, max_len, label = best
    if 5 * dist <= max_len:
        level = "拒"
    elif 5 * dist <= 2 * max_len:
        level = "扣"
    else:
        return None
    return {
        "rule": "R5",
        "level": level,
        "cand": label,
        "dist": dist,
        "max_len": max_len,
        "span": None,
    }


# --- 汇总 -------------------------------------------------------------------

def evaluate(password, username, email, lookup):
    """返回 (passed, score, rules)。lookup: key -> term 或 None。"""
    rules = [rule_r1(password)]
    base = rules[0]["base"]

    hit = rule_r2(password, lookup)
    if hit is not None:
        rules.append(hit)
    hit = rule_r3(password)
    if hit is not None:
        rules.append(hit)
    hit = rule_r4(password)
    if hit is not None:
        rules.append(hit)
    hit = rule_r5(password, username, email)
    r5_penalty = False
    if hit is not None:
        rules.append(hit)
        r5_penalty = hit["level"] == "扣"

    score = max(0, base - (20 if r5_penalty else 0))
    veto = any(
        entry["rule"] in ("R2", "R3", "R4")
        or (entry["rule"] == "R5" and entry["level"] == "拒")
        for entry in rules[1:]
    )
    passed = score >= 70 and not veto
    return passed, score, rules
