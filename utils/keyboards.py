"""
utils/keyboards.py — All InlineKeyboardMarkup builders in one place.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ─── Misc ─────────────────────────────────────────────────────────────────────

def join_channel_kb(channel: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📢 Join Channel", url=f"https://t.me/{channel.lstrip('@')}")
    b.button(text="✅ I've Joined — Verify", callback_data="verify_join")
    b.adjust(1)
    return b.as_markup()


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🛒 Shop", callback_data="shop")
    b.button(text="💰 Wallet", callback_data="wallet")
    b.button(text="🎁 Referral", callback_data="referral")
    b.button(text="📦 My Orders", callback_data="my_orders")
    b.adjust(2)
    return b.as_markup()


# ─── Shop ─────────────────────────────────────────────────────────────────────

def categories_kb(categories: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat in categories:
        stock = cat.get("stock", 0)
        b.button(
            text=f"{'🟢' if stock > 0 else '🔴'} {cat['name']} ({stock} left) — ₹{cat['price']:.0f}/ea",
            callback_data=f"cat_{cat['id']}",
        )
    b.button(text="🏠 Main Menu", callback_data="main_menu")
    b.adjust(1)
    return b.as_markup()


def quantity_kb(cat_id: int, stock: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for qty in [1, 2, 5, 10]:
        if qty <= stock:
            b.button(text=f"{qty}", callback_data=f"qty_{cat_id}_{qty}")
    b.button(text="✏️ Custom Qty", callback_data=f"qty_custom_{cat_id}")
    b.button(text="⬅️ Back", callback_data="shop")
    b.adjust(4, 1, 1)
    return b.as_markup()


def payment_kb(order_id: int, has_wallet: bool = False, wallet_enough: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ I Have Paid (UPI)", callback_data=f"paid_upi_{order_id}")
    if has_wallet and wallet_enough:
        b.button(text="💰 Pay from Wallet", callback_data=f"paid_wallet_{order_id}")
    b.button(text="❌ Cancel", callback_data=f"cancel_order_{order_id}")
    b.adjust(1)
    return b.as_markup()


# ─── Admin approval ───────────────────────────────────────────────────────────

def admin_approve_kb(order_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Approve", callback_data=f"approve_{order_id}")
    b.button(text="❌ Reject", callback_data=f"reject_{order_id}")
    b.adjust(2)
    return b.as_markup()


# ─── Admin Panel ──────────────────────────────────────────────────────────────

def admin_main_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📁 Categories", callback_data="adm_categories")
    b.button(text="🎟 Coupons/Stock", callback_data="adm_coupons")
    b.button(text="📦 Orders", callback_data="adm_orders")
    b.button(text="👥 Users", callback_data="adm_users")
    b.button(text="📊 Statistics", callback_data="adm_stats")
    b.button(text="⚙️ Settings", callback_data="adm_settings")
    b.button(text="📣 Broadcast", callback_data="adm_broadcast")
    b.adjust(2)
    return b.as_markup()


def admin_category_list_kb(categories: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat in categories:
        b.button(text=f"📁 {cat['name']} (stock:{cat.get('stock',0)})", callback_data=f"adm_cat_{cat['id']}")
    b.button(text="➕ Add Category", callback_data="adm_cat_add")
    b.button(text="⬅️ Back", callback_data="adm_main")
    b.adjust(1)
    return b.as_markup()


def admin_category_actions_kb(cat_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Edit", callback_data=f"adm_cat_edit_{cat_id}")
    b.button(text="🎟 Add Coupons", callback_data=f"adm_coupon_add_{cat_id}")
    b.button(text="📋 View Coupons", callback_data=f"adm_coupon_list_{cat_id}")
    b.button(text="🗑 Delete Category", callback_data=f"adm_cat_del_{cat_id}")
    b.button(text="⬅️ Back", callback_data="adm_categories")
    b.adjust(2, 2, 1)
    return b.as_markup()


def admin_settings_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💳 Set UPI ID", callback_data="adm_set_upi")
    b.button(text="🖼 Set QR Code", callback_data="adm_set_qr")
    b.button(text="📢 Set Channel", callback_data="adm_set_channel")
    b.button(text="🎁 Set Referral Bonus", callback_data="adm_set_refbonus")
    b.button(text="⬅️ Back", callback_data="adm_main")
    b.adjust(2, 2, 1)
    return b.as_markup()


def admin_orders_filter_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⏳ Pending", callback_data="adm_orders_pending")
    b.button(text="✅ Approved", callback_data="adm_orders_approved")
    b.button(text="❌ Rejected", callback_data="adm_orders_rejected")
    b.button(text="📋 All", callback_data="adm_orders_all")
    b.button(text="⬅️ Back", callback_data="adm_main")
    b.adjust(2, 2, 1)
    return b.as_markup()


def back_kb(callback: str = "main_menu") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Back", callback_data=callback)
    return b.as_markup()


def wallet_topup_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for amt in [50, 100, 200, 500]:
        b.button(text=f"₹{amt}", callback_data=f"topup_{amt}")
    b.button(text="✏️ Custom Amount", callback_data="topup_custom")
    b.button(text="⬅️ Back", callback_data="wallet")
    b.adjust(4, 1, 1)
    return b.as_markup()
