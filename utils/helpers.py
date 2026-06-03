"""
utils/helpers.py — Shared helper functions.
"""

import logging
from aiogram import Bot
from aiogram.types import Message, CallbackQuery
from database.db import get_setting, get_user, upsert_user
from config import REQUIRED_CHANNEL, ADMIN_IDS

logger = logging.getLogger(__name__)


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    """Check whether a user has joined the required channel."""
    channel = await get_setting("required_channel", REQUIRED_CHANNEL)
    if not channel:
        return True  # No channel configured → open access
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status not in ("left", "kicked", "banned")
    except Exception as e:
        logger.warning("Subscription check failed for %s: %s", user_id, e)
        return False  # Fail closed — require join if we can't verify


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def ensure_user(message_or_cq) -> None:
    """Upsert user record from any update type."""
    if isinstance(message_or_cq, Message):
        u = message_or_cq.from_user
    elif isinstance(message_or_cq, CallbackQuery):
        u = message_or_cq.from_user
    else:
        return
    await upsert_user(u.id, u.username, u.full_name)


def fmt_order(order: dict, include_user: bool = True) -> str:
    lines = [
        f"🆔 Order #{order['id']}",
        f"📁 {order['category_name']} × {order['quantity']}",
        f"💰 ₹{order['amount']:.2f}  via {order['paid_via'].upper()}",
        f"📅 {order['created_at']}",
        f"🔖 Status: {order['status'].upper()}",
    ]
    if include_user:
        lines.insert(1, f"👤 User: {order['user_id']}")
    return "\n".join(lines)


def fmt_stats(stats: dict) -> str:
    lines = [
        "📊 *Sales Statistics*",
        f"✅ Total Orders: `{stats['total_orders']}`",
        f"💰 Total Revenue: `₹{stats['total_revenue']}`",
        f"⏳ Pending: `{stats['pending_orders']}`",
        "",
        "*By Category:*",
    ]
    for cat in stats["by_category"]:
        lines.append(f"  • {cat['name']}: {cat['orders']} orders / ₹{cat['revenue']}")
    return "\n".join(lines)
