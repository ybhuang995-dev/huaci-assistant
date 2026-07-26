"""
历史记录模块
-----------
本地 SQLite 存储查询历史，支持按会话分组查阅。
由 Config.SAVE_HISTORY 开关控制是否写入。
"""

import sqlite3
import sys
import threading
from pathlib import Path
from datetime import datetime, timedelta

from config import Config

def _get_data_dir():
    """返回数据目录路径。—— 打包后使用 exe 所在目录，开发中使用项目根目录"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


_DB_PATH = _get_data_dir() / "history.db"
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接并确保表存在"""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS queries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  TEXT    NOT NULL,
            text       TEXT    NOT NULL,
            result     TEXT    NOT NULL,
            mode       TEXT    NOT NULL,
            mode_label TEXT    NOT NULL DEFAULT '',
            parent_id  INTEGER,
            root_id    INTEGER,
            FOREIGN KEY (parent_id) REFERENCES queries(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_queries_root
        ON queries(root_id, timestamp DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_queries_timestamp
        ON queries(timestamp DESC)
    """)
    return conn


def save(text: str, result: str, mode: str,
         parent_id: int | None = None,
         root_id: int | None = None) -> int | None:
    """写入一条查询记录。成功返回 id，失败返回 None。"""
    if not Config.SAVE_HISTORY:
        return None

    from config import MODES
    mode_label = MODES.get(mode, {}).get("label", mode)

    try:
        with _lock:
            conn = _get_conn()
            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            cursor = conn.execute(
                "INSERT INTO queries (timestamp, text, result, mode, mode_label, parent_id, root_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now, text, result, mode, mode_label, parent_id, root_id),
            )
            conn.commit()
            row_id = cursor.lastrowid

            # 如果是根查询，用自身 id 回填 root_id
            if root_id is None and parent_id is None:
                conn.execute(
                    "UPDATE queries SET root_id = ? WHERE id = ?",
                    (row_id, row_id),
                )
                conn.commit()

            conn.close()
            return row_id
    except Exception:
        return None


def get_recent(limit: int = 50, offset: int = 0) -> list[dict]:
    """取最近的根查询列表（不含追问子节点），按时间倒序。"""
    try:
        with _lock:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT id, timestamp, text, result, mode, mode_label, parent_id, root_id "
                "FROM queries WHERE parent_id IS NULL "
                "ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            conn.close()
        return [_row_to_dict(r) for r in rows]
    except Exception:
        return []


def get_chain(root_id: int) -> list[dict]:
    """取某个根查询 + 其所有追问，按时间升序排列。"""
    try:
        with _lock:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT id, timestamp, text, result, mode, mode_label, parent_id, root_id "
                "FROM queries WHERE root_id = ? "
                "ORDER BY timestamp ASC",
                (root_id,),
            ).fetchall()
            conn.close()
        return [_row_to_dict(r) for r in rows]
    except Exception:
        return []


def delete_query(query_id: int) -> bool:
    """删除一条记录及其所有子追问（级联）。"""
    try:
        with _lock:
            conn = _get_conn()
            conn.execute("DELETE FROM queries WHERE id = ?", (query_id,))
            conn.execute("DELETE FROM queries WHERE parent_id = ?", (query_id,))
            conn.commit()
            conn.close()
        return True
    except Exception:
        return False


def delete_all() -> bool:
    """清空全部历史记录。"""
    try:
        with _lock:
            conn = _get_conn()
            conn.execute("DELETE FROM queries")
            conn.commit()
            conn.close()
        return True
    except Exception:
        return False


def delete_old(days: int = 30) -> int:
    """清理超过 N 天的旧记录。返回删除行数。"""
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        with _lock:
            conn = _get_conn()
            cursor = conn.execute(
                "DELETE FROM queries WHERE timestamp < ?", (cutoff,)
            )
            conn.commit()
            deleted = cursor.rowcount
            conn.close()
        return deleted
    except Exception:
        return 0


def count() -> int:
    """返回历史记录总数（仅根查询）。"""
    try:
        with _lock:
            conn = _get_conn()
            row = conn.execute(
                "SELECT COUNT(*) FROM queries WHERE parent_id IS NULL"
            ).fetchone()
            conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def _row_to_dict(row: tuple) -> dict:
    """SQLite 行 → dict"""
    return {
        "id": row[0],
        "timestamp": row[1],
        "text": row[2],
        "result": row[3],
        "mode": row[4],
        "mode_label": row[5],
        "parent_id": row[6],
        "root_id": row[7],
    }
