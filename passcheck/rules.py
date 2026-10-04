"""R1/R3/R4/R5 规则与字符工具（R2 的查表由 wordlist 模块负责）。"""

FOLD_MAP = str.maketrans({
    "@": "a",
    "0": "o",
    "1": "i",
    "2": "z",
    "3": "e",
    "4": "a",
    "5": "s",
    "6": "g",
    "7": "t",
    "8": "b",
    "9": "g",
    "$": "s",
    "!": "i",
    "+": "t",
})

KEYBOARD_ROWS = (
    "`1234567890-=",
    "qwertyuiop[]\\",
    "asdfghjkl;'",
    "zxcvbnm,./",
)

_KEY_POS = {}
for _row_no, _row in enumerate(KEYBOARD_ROWS):
    for _col, _ch in enumerate(_row):
        _KEY_POS[_ch] = (_row_no, _col)


def fold(s):
    """形近替换（逐字符），长度不变。"""
    return s.translate(FOLD_MAP)


def char_class(ch):
    o = ord(ch)
    if 0x61 <= o <= 0x7A:
        return "L"
    if 0x41 <= o <= 0x5A:
        return "U"
    if 0x30 <= o <= 0x39:
        return "D"
    if 33 <= o <= 47 or 58 <= o <= 64 or 91 <= o <= 96 or 123 <= o <= 126:
        return "S"
    return "O"


def trim_bounds(s):
    """返回 (前导 D/S 数, 尾部 D/S 数)。"""
    n = len(s)
    lead = 0
    while lead < n and char_class(s[lead]) in ("D", "S"):
        lead += 1
    trail = 0
    while trail < n - lead and char_class(s[n - 1 - trail]) in ("D", "S"):
        trail += 1
    return lead, trail


def base_score(password):
    """R1 基准分。"""
    n = len(password)
    if n < 8:
        return 0
    classes = {char_class(ch) for ch in password}
    return min(100, min(n, 16) * 4 + (len(classes) - 1) * 9)


def keyboard_run(low):
    """R3：小写折叠串里最长键盘行走。

    返回 (起, 止)（右开，low 下标）或 None。行走向必须单调（全 +1 或全 -1
    列）；取最长，并列取起点最小，同起点正向优先。
    """
    n = len(low)
    best_start = 0
    best_len = 0
    for start in range(n):
        if n - start <= best_len:
            break
        pos0 = _KEY_POS.get(low[start])
        if pos0 is None:
            continue
        row, col0 = pos0
        for step in (1, -1):
            col = col0
            end = start
            while end + 1 < n:
                pos1 = _KEY_POS.get(low[end + 1])
                if pos1 is None or pos1[0] != row or pos1[1] != col + step:
                    break
                col += step
                end += 1
            run_len = end - start + 1
            if run_len > best_len:
                best_len = run_len
                best_start = start
    if best_len >= 4:
        return best_start, best_start + best_len
    return None


def repeat_unit(s):
    """R4：返回 (unit, repeat)，取最小可行 m；不命中返回 None。"""
    n = len(s)
    for m in (1, 2, 3):
        if n % m != 0:
            continue
        repeat = n // m
        if repeat >= 3 and s == s[:m] * repeat:
            return s[:m], repeat
    return None


def levenshtein(a, b):
    """Levenshtein 编辑距离（逐码点，增删改各 1）。"""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(
                prev[j] + 1,
                cur[j - 1] + 1,
                prev[j - 1] + (0 if ca == cb else 1),
            ))
        prev = cur
    return prev[-1]


def user_similarity(low, username, email):
    """R5：返回规则条目（拒/扣）或 None。"""
    candidates = []
    if username:
        candidates.append(("username", username))
    if "@" in username:
        prefix = username.partition("@")[0]
        if prefix:
            candidates.append(("username-local", prefix))
    if email:
        candidates.append(("email", email))
    if "@" in email:
        prefix = email.partition("@")[0]
        if prefix:
            candidates.append(("email-local", prefix))

    best = None
    for name, value in candidates:
        cand_low = value.lower()
        max_len = max(len(low), len(cand_low))
        if max_len == 0:
            continue
        dist = levenshtein(low, cand_low)
        if best is None or dist * best[2] < best[1] * max_len:
            best = (name, dist, max_len)

    if best is None:
        return None
    name, dist, max_len = best
    if 5 * dist <= max_len:
        level = "拒"
    elif 5 * dist <= 2 * max_len:
        level = "扣"
    else:
        return None
    return {
        "rule": "R5",
        "level": level,
        "cand": name,
        "dist": dist,
        "max_len": max_len,
        "span": None,
    }
