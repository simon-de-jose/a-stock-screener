"""SQLite 数据库初始化 + 查询封装"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """建表（幂等）"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stocks (
            code        TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            market      TEXT NOT NULL,
            price       REAL DEFAULT 0,
            market_cap  REAL DEFAULT 0,
            is_limit_up INTEGER DEFAULT 0,
            updated_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS concepts (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stock_concepts (
            stock_code TEXT NOT NULL,
            concept_id INTEGER NOT NULL,
            PRIMARY KEY (stock_code, concept_id),
            FOREIGN KEY (stock_code) REFERENCES stocks(code),
            FOREIGN KEY (concept_id) REFERENCES concepts(id)
        );
        CREATE INDEX IF NOT EXISTS idx_stock_concepts_concept
            ON stock_concepts(concept_id);
        CREATE INDEX IF NOT EXISTS idx_stocks_name
            ON stocks(name);
    """)
    conn.close()


# ── 写入 ──────────────────────────────────────────────

def upsert_stocks(rows: list[dict]):
    """批量写入/更新股票，rows = [{code, name, market, price, market_cap}]"""
    conn = get_conn()
    conn.executemany("""
        INSERT INTO stocks (code, name, market, price, market_cap, updated_at)
        VALUES (:code, :name, :market, :price, :market_cap, datetime('now'))
        ON CONFLICT(code) DO UPDATE SET
            name=excluded.name, market=excluded.market,
            price=excluded.price, market_cap=excluded.market_cap,
            updated_at=excluded.updated_at
    """, rows)
    conn.commit()
    conn.close()


def upsert_concept(name: str) -> int:
    """写入概念并返回 id"""
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO concepts (name) VALUES (?)", (name,))
    row = conn.execute("SELECT id FROM concepts WHERE name=?", (name,)).fetchone()
    conn.commit()
    conn.close()
    return row["id"]


def link_stock_concept(stock_code: str, concept_id: int):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO stock_concepts (stock_code, concept_id) VALUES (?,?)",
        (stock_code, concept_id),
    )
    conn.commit()
    conn.close()


def batch_link_stock_concepts(pairs: list[tuple]):
    """批量关联 [(stock_code, concept_id), ...]"""
    conn = get_conn()
    conn.executemany(
        "INSERT OR IGNORE INTO stock_concepts (stock_code, concept_id) VALUES (?,?)",
        pairs,
    )
    conn.commit()
    conn.close()


def mark_limit_up(codes: set[str]):
    """标记涨停股"""
    conn = get_conn()
    conn.execute("UPDATE stocks SET is_limit_up=0")
    if codes:
        placeholders = ",".join("?" for _ in codes)
        conn.execute(
            f"UPDATE stocks SET is_limit_up=1 WHERE code IN ({placeholders})",
            list(codes),
        )
    conn.commit()
    conn.close()


# ── 查询 ──────────────────────────────────────────────

def get_stock_by_name(name: str) -> dict | None:
    conn = get_conn()
    # 先精确匹配，再模糊匹配
    row = conn.execute("SELECT * FROM stocks WHERE name=?", (name,)).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM stocks WHERE name LIKE ? LIMIT 1", (f'%{name}%',)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_concepts_for_stock(code: str) -> list[str]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.name FROM concepts c
        JOIN stock_concepts sc ON sc.concept_id = c.id
        WHERE sc.stock_code = ?
    """, (code,)).fetchall()
    conn.close()
    return [r["name"] for r in rows]


def code_to_market(code: str) -> str:
    if code.startswith("60"):
        return "主板"
    if code.startswith("00"):
        return "主板"
    if code.startswith("30"):
        return "创业板"
    if code.startswith("68"):
        return "科创板"
    if code.startswith(("8", "4")):
        return "北交所"
    return "其他"


def search_match(
    chars: list[str],
    concept_ids: list[int],
    markets: list[str],
    char_mode: str = "or",
) -> list[dict]:
    """
    组合条件搜索：
    - chars: 字匹配列表
    - concept_ids: 概念 id 列表
    - markets: 交易所列表
    - char_mode: "or" 包含任一字 / "and" 包含所有字
    三个条件取交集
    """
    conn = get_conn()
    conditions = []
    params = []

    # 字匹配
    if chars:
        if char_mode == "and":
            for ch in chars:
                conditions.append("s.name LIKE ?")
                params.append(f"%{ch}%")
        else:
            or_clauses = " OR ".join("s.name LIKE ?" for _ in chars)
            conditions.append(f"({or_clauses})")
            params.extend(f"%{ch}%" for ch in chars)

    # 概念匹配
    if concept_ids:
        placeholders = ",".join("?" for _ in concept_ids)
        conditions.append(f"""
            s.code IN (
                SELECT stock_code FROM stock_concepts
                WHERE concept_id IN ({placeholders})
            )
        """)
        params.extend(concept_ids)

    # 交易所
    if markets:
        placeholders = ",".join("?" for _ in markets)
        conditions.append(f"s.market IN ({placeholders})")
        params.extend(markets)

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"""
        SELECT s.*, GROUP_CONCAT(c.name, '、') AS concept_names
        FROM stocks s
        LEFT JOIN stock_concepts sc ON sc.stock_code = s.code
        LEFT JOIN concepts c ON c.id = sc.concept_id
        WHERE {where}
        GROUP BY s.code
        ORDER BY s.is_limit_up DESC, s.market_cap DESC
        LIMIT 500
    """
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print("数据库初始化完成 ✓")
