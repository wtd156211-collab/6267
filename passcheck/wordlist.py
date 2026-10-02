"""常见口令词表：读取、去重、落盘索引（sqlite3，标准库）。

索引只放派生数据，删掉 var/ 后按词表内容重建，结果不变。
索引与词表内容绑定：清单记录每个词表文件的名字/大小/SHA-256，
对不上就重建。查询是精确整串匹配，不用任何近似结构。
"""

import hashlib
import json
import os
import sqlite3

FORMAT_VERSION = 1
INDEX_FILENAME = "wordlist-index.sqlite3"


class InputError(Exception):
    """输入不可用（缺文件、解析失败等），对应退出码 1。"""


def list_wordlist_files(wordlists_dir):
    """按文件名字典序列出 *.txt 词表文件。"""
    try:
        entries = os.listdir(wordlists_dir)
    except OSError as exc:
        raise InputError("词表目录不可读: %s (%s)" % (wordlists_dir, exc))
    names = sorted(
        name for name in entries
        if name.endswith(".txt")
        and os.path.isfile(os.path.join(wordlists_dir, name))
    )
    if not names:
        raise InputError("词表目录里没有 .txt 文件: %s" % wordlists_dir)
    return [os.path.join(wordlists_dir, name) for name in names]


def _file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(paths):
    files = []
    for path in paths:
        try:
            size = os.path.getsize(path)
            sha = _file_sha256(path)
        except OSError as exc:
            raise InputError("词表文件不可读: %s (%s)" % (path, exc))
        files.append({"name": os.path.basename(path), "size": size, "sha256": sha})
    return {"format": FORMAT_VERSION, "files": files}


def iter_words(paths):
    """按文件名字典序逐行产出词表词条；跳过空行与 # 开头行。"""
    for path in paths:
        try:
            fh = open(path, "r", encoding="utf-8", newline="")
        except OSError as exc:
            raise InputError("词表文件不可读: %s (%s)" % (path, exc))
        with fh:
            for line in fh:
                word = line.rstrip("\n")
                if not word or word.startswith("#"):
                    continue
                yield word


def _configure(conn):
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA cache_size=-2048")  # 2 MiB，控制内存


def _build(conn, paths):
    conn.execute(
        "CREATE TABLE terms (key TEXT PRIMARY KEY, term TEXT NOT NULL) WITHOUT ROWID"
    )
    batch = []
    cursor = conn.cursor()
    for word in iter_words(paths):
        # 小写后同词的只留先出现那份的写法：INSERT OR IGNORE 保首次
        batch.append((word.lower(), word))
        if len(batch) >= 20000:
            cursor.executemany(
                "INSERT OR IGNORE INTO terms (key, term) VALUES (?, ?)", batch
            )
            batch.clear()
    if batch:
        cursor.executemany(
            "INSERT OR IGNORE INTO terms (key, term) VALUES (?, ?)", batch
        )
    conn.commit()


class WordIndex:
    """词表索引句柄；lookup(key) 返回词表原词或 None。"""

    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor()

    def lookup(self, key):
        row = self._cursor.execute(
            "SELECT term FROM terms WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row is not None else None

    def close(self):
        self._conn.close()


def open_index(wordlists_dir, var_dir):
    """打开词表索引；缺失或内容对不上时重建。返回 WordIndex。"""
    paths = list_wordlist_files(wordlists_dir)
    wanted = _manifest(paths)
    os.makedirs(var_dir, exist_ok=True)
    index_path = os.path.join(var_dir, INDEX_FILENAME)

    if os.path.exists(index_path):
        conn = None
        matched = False
        try:
            conn = sqlite3.connect(index_path)
            _configure(conn)
            row = conn.execute(
                "SELECT value FROM meta WHERE k = 'manifest'"
            ).fetchone()
            matched = row is not None and json.loads(row[0]) == wanted
        except (sqlite3.Error, ValueError, KeyError):
            matched = False
        if matched:
            return WordIndex(conn)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        # 词表变了或索引损坏：重建
        try:
            os.remove(index_path)
        except OSError:
            pass

    tmp_path = index_path + ".tmp"
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    conn = sqlite3.connect(tmp_path)
    try:
        _configure(conn)
        conn.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
        conn.execute(
            "INSERT INTO meta (k, v) VALUES ('manifest', ?)",
            (json.dumps(wanted, ensure_ascii=False, sort_keys=True),),
        )
        _build(conn, paths)
        conn.commit()
        conn.close()
    except BaseException:
        conn.close()
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    os.replace(tmp_path, index_path)
    conn = sqlite3.connect(index_path)
    _configure(conn)
    return WordIndex(conn)
