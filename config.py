"""
config.py — Central configuration loader.
All values come from environment variables (set in Railway or .env file).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Bot ──────────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_IDS: list[int] = [
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
]

# ─── Channel Gate ─────────────────────────────────────────────────────────────
REQUIRED_CHANNEL: str = os.getenv("REQUIRED_CHANNEL", "")   # e.g. @mychannel or -100...

# ─── Database ─────────────────────────────────────────────────────────────────
DB_PATH: str = os.getenv("DB_PATH", "shop.db")

# ─── Referral ─────────────────────────────────────────────────────────────────
REFERRAL_BONUS: float = float(os.getenv("REFERRAL_BONUS", "10.0"))   # ₹ added to wallet

# ─── Misc ─────────────────────────────────────────────────────────────────────
CURRENCY_SYMBOL: str = os.getenv("CURRENCY_SYMBOL", "₹")
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "")          # without @, for referral links

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is required")
