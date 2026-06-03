"""
database/db.py — Async SQLite layer (aiosqlite).

Tables
------
users          — registered users, wallet, referral tracking
categories     — product categories with price per unit
coupons        — individual coupon codes tied to a category
orders         — completed + pending orders
settings       — key/value store (UPI, QR path, channel, etc.)
referrals      — who referred whom (prevent double credit)
"""

import aiosqlite
import logging
from datetime import datetime
from config import DB_PATH

logger = logging.getLogger(__name__)

# ─────────────────────────── Schema ──────────────────────────────────────────

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    wallet      REAL    DEFAULT 0.0,
    referral_code TEXT  UNIQUE,
    referred_by INTEGER,
    joined_at   TEXT    DEFAULT (datetime('now')),
    is_banned   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    price       REAL    NOT NULL,
    description TEXT    DEFAULT '',
    is_active   INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS coupons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    code        TEXT    NOT NULL,
    is_used     INTEGER DEFAULT 0,
    used_by     INTEGER,
    used_at     TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    category_id   INTEGER NOT NULL,
    category_name TEXT,
    quantity      INTEGER NOT NULL,
    amount        REAL    NOT NULL,
    paid_via      TEXT    DEFAULT 'upi',   -- 'upi' | 'wallet'
    status        TEXT    DEFAULT 'pending', -- pending | approved | rejected
    admin_id      INTEGER,
    created_at    TEXT    DEFAULT (datetime('now')),
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS referrals (
    referrer_id INTEGER,
    referred_id INTEGER PRIMARY KEY,
    credited    INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_coupons_category ON coupons(category_id, is_used);
CREATE INDEX IF NOT EXISTS idx_orders_user      ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status    ON orders(status);
"""

# ─────────────────────────── Bootstrap ───────────────────────────────────────

async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info("Database initialised at %s", DB_PATH)

# ─────────────────────────── Settings ────────────────────────────────────────

async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
    return row[0] if row else default

async def set_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await db.commit()

# ─────────────────────────── Users ───────────────────────────────────────────

async def upsert_user(user_id: int, username: str, full_name: str) -> None:
    """Register or update a user. Does NOT overwrite wallet."""
    import random, string
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=7))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users(user_id, username, full_name, referral_code)
               VALUES(?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE
               SET username=excluded.username,
                   full_name=excluded.full_name""",
            (user_id, username or "", full_name or "", code),
        )
        await db.commit()

async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None

async def get_user_by_referral(code: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE referral_code=?", (code,)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None

async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE is_banned=0") as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]

async def get_user_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_banned=0") as cur:
            row = await cur.fetchone()
    return row[0] if row else 0

async def update_wallet(user_id: int, delta: float) -> float:
    """Add (positive) or deduct (negative) from wallet. Returns new balance."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET wallet = wallet + ? WHERE user_id=?", (delta, user_id)
        )
        await db.commit()
        async with db.execute("SELECT wallet FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0.0

async def ban_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
        await db.commit()

async def unban_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
        await db.commit()

# ─────────────────────────── Referrals ───────────────────────────────────────

async def record_referral(referrer_id: int, referred_id: int) -> bool:
    """Returns True if this is a new referral (not already recorded)."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO referrals(referrer_id, referred_id) VALUES(?,?)",
                (referrer_id, referred_id),
            )
            await db.execute(
                "UPDATE users SET referred_by=? WHERE user_id=?",
                (referrer_id, referred_id),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def credit_referral_bonus(referrer_id: int, referred_id: int, bonus: float) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET wallet=wallet+? WHERE user_id=?", (bonus, referrer_id))
        await db.execute(
            "UPDATE referrals SET credited=1 WHERE referrer_id=? AND referred_id=?",
            (referrer_id, referred_id),
        )
        await db.commit()

# ─────────────────────────── Categories ──────────────────────────────────────

async def add_category(name: str, price: float, description: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO categories(name,price,description) VALUES(?,?,?)",
            (name, price, description),
        )
        await db.commit()
        return cur.lastrowid

async def get_categories(active_only: bool = True) -> list[dict]:
    q = "SELECT c.*, COUNT(CASE WHEN cp.is_used=0 THEN 1 END) AS stock FROM categories c LEFT JOIN coupons cp ON cp.category_id=c.id"
    if active_only:
        q += " WHERE c.is_active=1"
    q += " GROUP BY c.id ORDER BY c.name"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(q) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]

async def get_category(cat_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT c.*, COUNT(CASE WHEN cp.is_used=0 THEN 1 END) AS stock "
            "FROM categories c LEFT JOIN coupons cp ON cp.category_id=c.id "
            "WHERE c.id=? GROUP BY c.id",
            (cat_id,),
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None

async def edit_category(cat_id: int, name: str, price: float, description: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE categories SET name=?,price=?,description=? WHERE id=?",
            (name, price, description, cat_id),
        )
        await db.commit()

async def delete_category(cat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM categories WHERE id=?", (cat_id,))
        await db.commit()

async def toggle_category(cat_id: int, active: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE categories SET is_active=? WHERE id=?", (int(active), cat_id))
        await db.commit()

# ─────────────────────────── Coupons / Stock ─────────────────────────────────

async def add_coupons(category_id: int, codes: list[str]) -> int:
    """Bulk-insert coupon codes. Returns number inserted."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT INTO coupons(category_id, code) VALUES(?,?)",
            [(category_id, c.strip()) for c in codes if c.strip()],
        )
        await db.commit()
    return len(codes)

async def get_stock(category_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM coupons WHERE category_id=? AND is_used=0", (category_id,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0

async def fetch_and_mark_coupons(category_id: int, qty: int, order_id: int, user_id: int) -> list[str]:
    """Atomically claim `qty` unused coupons for this order."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, code FROM coupons WHERE category_id=? AND is_used=0 LIMIT ?",
            (category_id, qty),
        ) as cur:
            rows = await cur.fetchall()
        if len(rows) < qty:
            return []
        ids = [r[0] for r in rows]
        codes = [r[1] for r in rows]
        await db.execute(
            f"UPDATE coupons SET is_used=1, used_by=?, used_at=? WHERE id IN ({','.join('?'*len(ids))})",
            [user_id, now] + ids,
        )
        await db.commit()
    return codes

async def delete_coupon(coupon_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM coupons WHERE id=?", (coupon_id,))
        await db.commit()

async def list_coupons(category_id: int, used: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM coupons WHERE category_id=? AND is_used=?", (category_id, int(used))
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]

# ─────────────────────────── Orders ──────────────────────────────────────────

async def create_order(
    user_id: int,
    category_id: int,
    category_name: str,
    quantity: int,
    amount: float,
    paid_via: str = "upi",
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO orders(user_id,category_id,category_name,quantity,amount,paid_via) VALUES(?,?,?,?,?,?)",
            (user_id, category_id, category_name, quantity, amount, paid_via),
        )
        await db.commit()
        return cur.lastrowid

async def get_order(order_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE id=?", (order_id,)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None

async def update_order_status(order_id: int, status: str, admin_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status=?,admin_id=?,updated_at=datetime('now') WHERE id=?",
            (status, admin_id, order_id),
        )
        await db.commit()

async def get_orders(status: str | None = None, limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status:
            async with db.execute(
                "SELECT * FROM orders WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cur:
                rows = await cur.fetchall()
    return [dict(r) for r in rows]

async def get_user_orders(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]

# ─────────────────────────── Sales Statistics ────────────────────────────────

async def get_sales_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*), SUM(amount) FROM orders WHERE status='approved'"
        ) as cur:
            row = await cur.fetchone()
        total_orders, total_revenue = (row[0] or 0), (row[1] or 0.0)

        async with db.execute(
            "SELECT category_name, COUNT(*), SUM(amount) FROM orders WHERE status='approved' GROUP BY category_name ORDER BY SUM(amount) DESC"
        ) as cur:
            by_cat = await cur.fetchall()

        async with db.execute(
            "SELECT COUNT(*) FROM orders WHERE status='pending'"
        ) as cur:
            pending = (await cur.fetchone())[0]

    return {
        "total_orders": total_orders,
        "total_revenue": round(total_revenue, 2),
        "pending_orders": pending,
        "by_category": [
            {"name": r[0], "orders": r[1], "revenue": round(r[2], 2)} for r in by_cat
        ],
    }
