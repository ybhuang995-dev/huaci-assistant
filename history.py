"""
历史记录模块
-----------
本地 SQLite 存储查询历史，支持按会话分组查阅。
由 Config.SAVE_HISTORY 开关控制是否写入。

v2：增加 visible 列 + 节点阈值控制，只有对话链节点数达到阈值才在列表中显示。
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
            visible    INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (parent_id) REFERENCES queries(id) ON DELETE CASCADE
        )
    """)
    # 迁移：旧表可能没有 visible 列
    try:
        conn.execute("ALTER TABLE queries ADD COLUMN visible INTEGER NOT NULL DEFAULT 0")
        # 将已有记录的 visible 设为 1（避免旧数据丢失）
        conn.execute("UPDATE queries SET visible = 1 WHERE parent_id IS NULL")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 列已存在

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_queries_root
        ON queries(root_id, timestamp DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_queries_timestamp
        ON queries(timestamp DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_queries_visible
        ON queries(visible, parent_id, timestamp DESC)
    """)
    return conn


def _count_chain(conn: sqlite3.Connection, root_id: int) -> int:
    """统计某个 root_id 下的总节点数"""
    row = conn.execute(
        "SELECT COUNT(*) FROM queries WHERE root_id = ?", (root_id,)
    ).fetchone()
    return row[0] if row else 0


def _set_chain_visible(conn: sqlite3.Connection, root_id: int,
                       visible: bool) -> None:
    """将整条链的 visible 标记设置为指定值"""
    conn.execute(
        "UPDATE queries SET visible = ? WHERE root_id = ?",
        (1 if visible else 0, root_id),
    )
    conn.commit()


def save(text: str, result: str, mode: str,
         parent_id: int | None = None,
         root_id: int | None = None) -> int | None:
    """写入一条查询记录。成功返回 id，失败返回 None。

    保存后自动检查节点数是否达到阈值：
    - 达到 → 标记整条链 visible = 1
    - 未达到 → 保持 visible = 0（不在列表中显示，但数据已保存）
    """
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
            actual_root_id = root_id
            if root_id is None and parent_id is None:
                actual_root_id = row_id
                conn.execute(
                    "UPDATE queries SET root_id = ? WHERE id = ?",
                    (row_id, row_id),
                )
                conn.commit()

            # ── 节点阈值检查 ──
            if actual_root_id is not None:
                chain_count = _count_chain(conn, actual_root_id)
                if chain_count >= Config.HISTORY_MIN_NODES:
                    _set_chain_visible(conn, actual_root_id, True)

            conn.close()
            return row_id
    except Exception:
        return None


def get_history_list(limit: int = 50, offset: int = 0) -> list[dict]:
    """返回历史列表：每个根查询 + 链节点数统计，按时间倒序。

    只返回 visible = 1 的根记录（即节点数达到阈值的会话）。
    """
    try:
        with _lock:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT q.id, q.timestamp, q.text, q.result, q.mode, "
                "       q.mode_label, q.parent_id, q.root_id, "
                "       (SELECT COUNT(*) FROM queries c "
                "        WHERE c.root_id = q.root_id) AS chain_count "
                "FROM queries q "
                "WHERE q.parent_id IS NULL AND q.visible = 1 "
                "ORDER BY q.timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) FROM queries "
                "WHERE parent_id IS NULL AND visible = 1"
            ).fetchone()[0]
            conn.close()

        result = []
        for r in rows:
            result.append({
                "id": r[0],
                "timestamp": r[1],
                "text": r[2],
                "result": r[3],
                "mode": r[4],
                "mode_label": r[5],
                "parent_id": r[6],
                "root_id": r[7],
                "chain_count": r[8],
            })
        return result
    except Exception:
        return []


def get_history_total() -> int:
    """返回可见历史记录总数"""
    try:
        with _lock:
            conn = _get_conn()
            row = conn.execute(
                "SELECT COUNT(*) FROM queries "
                "WHERE parent_id IS NULL AND visible = 1"
            ).fetchone()
            conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def get_recent(limit: int = 50, offset: int = 0) -> list[dict]:
    """取最近的根查询列表（仅可见的），按时间倒序。"""
    try:
        with _lock:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT id, timestamp, text, result, mode, mode_label, parent_id, root_id "
                "FROM queries WHERE parent_id IS NULL AND visible = 1 "
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
    """返回历史记录总数（仅可见根查询）。"""
    try:
        with _lock:
            conn = _get_conn()
            row = conn.execute(
                "SELECT COUNT(*) FROM queries WHERE parent_id IS NULL AND visible = 1"
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
