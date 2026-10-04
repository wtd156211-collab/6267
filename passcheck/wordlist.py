"""R2 词表：精确索引，落 var/，与词表内容绑定。

索引用标准库 sqlite3 存 (小写键 -> 词表原词)。查询精确、零漏判；
堆占用主要在原生侧，Python 堆峰值远低于预算。词表内容变化时
按指纹自动重建；删掉 var/ 结果不变，只是重建慢些。
"""

import hashlib
import os
import sqlite3

_BATCH = 8192


class WordlistError(Exception):
    """词表输入不可用。"""


def list_wordlists(wordlists_dir):
    """按文件名字典序列出词表文件。"""
    if not os.path.isdir(wordlists_dir):
        raise WordlistError("词表目录不可用: %s" % wordlists_dir)
    names = sorted(
        name for name in os.listdir(wordlists_dir)
        if name.endswith(".txt") and os.path.isfile(os.path.join(wordlists_dir, name))
    )
    if not names:
        raise WordlistError("词表目录下没有 .txt 文件: %s" % wordlists_dir)
    return [os.path.join(wordlists_dir, name) for name in names]


def _fingerprint(paths):
    """词表集合内容指纹：文件名 + 文件内容哈希，按序串联。"""
    digest = hashlib.sha256()
    for path in paths:
        digest.update(os.path.basename(path).encode("utf-8"))
        digest.update(b"\0")
        file_hash = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                file_hash.update(chunk)
        digest.update(file_hash.digest())
    return digest.hexdigest()


def _iter_terms(path):
    """逐行产出词表词条：跳过空行与 # 开头行。"""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            word = line.rstrip("\n")
            if word.endswith("\r"):
                word = word[:-1]
            if not word or word.startswith("#"):
                continue
            yield word


class WordlistIndex:
    """词表精确索引。open() 复用或重建；lookup() 精确查键。"""

    def __init__(self, index_path):
        self.index_path = index_path
        self._conn = None

    def open(self, wordlist_paths):
        """绑定词表集合；索引缺失或指纹不符时重建。返回是否重建。"""
        fingerprint = _fingerprint(wordlist_paths)
        conn = self._try_open(fingerprint)
        if conn is not None:
            self._conn = conn
            return False
        self._build(wordlist_paths, fingerprint)
        return True

    def _try_open(self, fingerprint):
        if not os.path.exists(self.index_path):
            return None
        try:
            conn = sqlite3.connect(self.index_path)
            row = conn.execute(
                "SELECT v FROM meta WHERE k = 'fingerprint'"
            ).fetchone()
        except sqlite3.Error:
            conn = None
            row = None
        if row is not None and row[0] == fingerprint:
            return conn
        if conn is not None:
            conn.close()
        return None

    def _build(self, wordlist_paths, fingerprint):
        directory = os.path.dirname(self.index_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = self.index_path + ".tmp"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        conn = sqlite3.connect(tmp_path)
        try:
            conn.execute("PRAGMA journal_mode = OFF")
            conn.execute("PRAGMA synchronous = OFF")
            conn.execute(
                "CREATE TABLE terms (key TEXT PRIMARY KEY, term TEXT) WITHOUT ROWID"
            )
            conn.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
            batch = []
            for path in wordlist_paths:
                for word in _iter_terms(path):
                    # 小写后同词只留先出现那份的写法。
                    batch.append((word.lower(), word))
                    if len(batch) >= _BATCH:
                        conn.executemany(
                            "INSERT OR IGNORE INTO terms (key, term) VALUES (?, ?)",
                            batch,
                        )
                        batch.clear()
            if batch:
                conn.executemany(
                    "INSERT OR IGNORE INTO terms (key, term) VALUES (?, ?)", batch
                )
            conn.execute(
                "INSERT INTO meta (k, v) VALUES ('fingerprint', ?)", (fingerprint,)
            )
            conn.commit()
            conn.close()
        except BaseException:
            conn.close()
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
        os.replace(tmp_path, self.index_path)
        self._conn = sqlite3.connect(self.index_path)

    def lookup(self, keys):
        """精确查键：{key: term}。键不存在则不出现，绝不漏判。"""
        if not keys:
            return {}
        if self._conn is None:
            raise WordlistError("词表索引尚未打开")
        placeholders = ",".join("?" * len(keys))
        cursor = self._conn.execute(
            "SELECT key, term FROM terms WHERE key IN (%s)" % placeholders,
            list(keys),
        )
        return {key: term for key, term in cursor}

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
