"""
handlers/admin.py — Full admin panel.

Features:
 • Category CRUD
 • Coupon upload (bulk, one per line)
 • Stock overview
 • Order management + approval/rejection
 • Sales statistics
 • Settings (UPI, QR, Channel, Referral Bonus)
 • Broadcast
 • User list / ban / unban
"""

import logging
import os
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from database.db import (
    get_categories, get_category, add_category, edit_category,
    delete_category, toggle_category,
    add_coupons, list_coupons, get_stock,
    get_orders, get_order, update_order_status, fetch_and_mark_coupons,
    get_user_count, get_all_users, ban_user, unban_user,
    get_sales_stats, get_setting, set_setting, get_user,
)
from utils.keyboards import (
    admin_main_kb, admin_category_list_kb, admin_category_actions_kb,
    admin_settings_kb, admin_orders_filter_kb, back_kb,
)
from utils.helpers import is_admin, fmt_order, fmt_stats
from utils.states import AdminCategoryStates, AdminCouponStates, AdminSettingStates, AdminBroadcastStates
from config import ADMIN_IDS, CURRENCY_SYMBOL

router = Router()
logger = logging.getLogger(__name__)


# ─────────────────────────── Access Guard ────────────────────────────────────

def admin_only(func):
    """Decorator — silently ignores non-admins."""
    async def wrapper(update, *args, **kwargs):
        uid = update.from_user.id if hasattr(update, "from_user") else None
        if uid not in ADMIN_IDS:
            if isinstance(update, CallbackQuery):
                await update.answer("🚫 Admins only.", show_alert=True)
            return
        return await func(update, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


# ─────────────────────────── Entry ───────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("🚫 Access denied.")
    users = await get_user_count()
    pending = len(await get_orders("pending"))
    await message.answer(
        f"👑 *Admin Panel*\n\n👥 Users: `{users}`\n⏳ Pending orders: `{pending}`",
        reply_markup=admin_main_kb(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "adm_main")
@admin_only
async def cb_adm_main(cq: CallbackQuery):
    users = await get_user_count()
    pending = len(await get_orders("pending"))
    await cq.message.edit_text(
        f"👑 *Admin Panel*\n\n👥 Users: `{users}`\n⏳ Pending orders: `{pending}`",
        reply_markup=admin_main_kb(),
        parse_mode="Markdown",
    )
    await cq.answer()


# ─────────────────────────── Categories ──────────────────────────────────────

@router.callback_query(F.data == "adm_categories")
@admin_only
async def cb_categories(cq: CallbackQuery):
    cats = await get_categories(active_only=False)
    await cq.message.edit_text(
        f"📁 *Categories* ({len(cats)} total)",
        reply_markup=admin_category_list_kb(cats),
        parse_mode="Markdown",
    )
    await cq.answer()


@router.callback_query(F.data.regexp(r"^adm_cat_\d+$"))
@admin_only
async def cb_category_view(cq: CallbackQuery):
    cat_id = int(cq.data.split("_")[2])
    cat = await get_category(cat_id)
    if not cat:
        return await cq.answer("Category not found.", show_alert=True)
    text = (
        f"📁 *{cat['name']}*\n"
        f"💰 Price: {CURRENCY_SYMBOL}{cat['price']:.2f}/unit\n"
        f"📦 Stock: {cat['stock']} available\n"
        f"📝 {cat['description'] or 'No description'}\n"
        f"Status: {'🟢 Active' if cat['is_active'] else '🔴 Inactive'}"
    )
    await cq.message.edit_text(text, reply_markup=admin_category_actions_kb(cat_id), parse_mode="Markdown")
    await cq.answer()


# Add category
@router.callback_query(F.data == "adm_cat_add")
@admin_only
async def cb_cat_add_start(cq: CallbackQuery, state: FSMContext):
    await cq.message.answer("📁 Enter new category *name*:", parse_mode="Markdown")
    await state.set_state(AdminCategoryStates.waiting_name)
    await cq.answer()


@router.message(AdminCategoryStates.waiting_name)
async def adm_cat_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(name=message.text.strip())
    await message.answer("💰 Enter *price per unit* (e.g. 49.99):", parse_mode="Markdown")
    await state.set_state(AdminCategoryStates.waiting_price)


@router.message(AdminCategoryStates.waiting_price)
async def adm_cat_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        price = float(message.text.strip())
    except ValueError:
        return await message.answer("❌ Invalid price. Enter a number like 49.99")
    await state.update_data(price=price)
    await message.answer("📝 Enter *description* (or send `-` to skip):", parse_mode="Markdown")
    await state.set_state(AdminCategoryStates.waiting_desc)


@router.message(AdminCategoryStates.waiting_desc)
async def adm_cat_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    desc = "" if message.text.strip() == "-" else message.text.strip()
    cat_id = await add_category(data["name"], data["price"], desc)
    await state.clear()
    await message.answer(
        f"✅ Category *{data['name']}* created (ID:{cat_id}).",
        reply_markup=admin_main_kb(),
        parse_mode="Markdown",
    )


# Edit category
@router.callback_query(F.data.startswith("adm_cat_edit_"))
@admin_only
async def cb_cat_edit_start(cq: CallbackQuery, state: FSMContext):
    cat_id = int(cq.data.split("_")[3])
    cat = await get_category(cat_id)
    if not cat:
        return await cq.answer("Not found.", show_alert=True)
    await state.update_data(cat_id=cat_id)
    await cq.message.answer(
        f"✏️ Editing *{cat['name']}*\nSend new name (or `-` to keep `{cat['name']}`):",
        parse_mode="Markdown",
    )
    await state.set_state(AdminCategoryStates.edit_name)
    await cq.answer()


@router.message(AdminCategoryStates.edit_name)
async def adm_cat_edit_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    cat = await get_category(data["cat_id"])
    name = cat["name"] if message.text.strip() == "-" else message.text.strip()
    await state.update_data(new_name=name)
    await message.answer(f"💰 New price (or `-` to keep {cat['price']}):")
    await state.set_state(AdminCategoryStates.edit_price)


@router.message(AdminCategoryStates.edit_price)
async def adm_cat_edit_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    cat = await get_category(data["cat_id"])
    if message.text.strip() == "-":
        price = cat["price"]
    else:
        try:
            price = float(message.text.strip())
        except ValueError:
            return await message.answer("❌ Invalid price.")
    await state.update_data(new_price=price)
    await message.answer(f"📝 New description (or `-` to keep):")
    await state.set_state(AdminCategoryStates.edit_desc)


@router.message(AdminCategoryStates.edit_desc)
async def adm_cat_edit_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    cat = await get_category(data["cat_id"])
    desc = cat["description"] if message.text.strip() == "-" else message.text.strip()
    await edit_category(data["cat_id"], data["new_name"], data["new_price"], desc)
    await state.clear()
    await message.answer("✅ Category updated.", reply_markup=admin_main_kb())


# Delete category
@router.callback_query(F.data.startswith("adm_cat_del_"))
@admin_only
async def cb_cat_delete(cq: CallbackQuery):
    cat_id = int(cq.data.split("_")[3])
    cat = await get_category(cat_id)
    if not cat:
        return await cq.answer("Not found.", show_alert=True)
    await delete_category(cat_id)
    await cq.answer(f"🗑 {cat['name']} deleted.", show_alert=True)
    cats = await get_categories(active_only=False)
    await cq.message.edit_text("📁 *Categories*", reply_markup=admin_category_list_kb(cats), parse_mode="Markdown")


# ─────────────────────────── Coupons ─────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_coupon_add_"))
@admin_only
async def cb_coupon_add(cq: CallbackQuery, state: FSMContext):
    cat_id = int(cq.data.split("_")[3])
    cat = await get_category(cat_id)
    await state.update_data(cat_id=cat_id, cat_name=cat["name"] if cat else "?")
    await cq.message.answer(
        f"🎟 Paste coupon codes for *{cat['name']}* — one per line:",
        parse_mode="Markdown",
    )
    await state.set_state(AdminCouponStates.waiting_codes)
    await cq.answer()


@router.message(AdminCouponStates.waiting_codes)
async def adm_coupon_codes(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    codes = [c for c in message.text.splitlines() if c.strip()]
    n = await add_coupons(data["cat_id"], codes)
    await state.clear()
    await message.answer(
        f"✅ Added *{n}* coupons to *{data['cat_name']}*.",
        reply_markup=admin_main_kb(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("adm_coupon_list_"))
@admin_only
async def cb_coupon_list(cq: CallbackQuery):
    cat_id = int(cq.data.split("_")[3])
    cat = await get_category(cat_id)
    available = await list_coupons(cat_id, used=False)
    used = await list_coupons(cat_id, used=True)
    text = (
        f"📋 *Coupons: {cat['name']}*\n\n"
        f"🟢 Available: {len(available)}\n"
        f"🔴 Used: {len(used)}\n\n"
    )
    if available:
        sample = "\n".join(c["code"] for c in available[:10])
        text += f"*Sample (first 10):*\n`{sample}`"
    await cq.message.answer(text, parse_mode="Markdown", reply_markup=back_kb("adm_categories"))
    await cq.answer()


# ─────────────────────────── Orders ──────────────────────────────────────────

@router.callback_query(F.data == "adm_orders")
@admin_only
async def cb_orders(cq: CallbackQuery):
    await cq.message.edit_text("📦 *Orders* — choose filter:", reply_markup=admin_orders_filter_kb(), parse_mode="Markdown")
    await cq.answer()


@router.callback_query(F.data.startswith("adm_orders_"))
@admin_only
async def cb_orders_list(cq: CallbackQuery):
    status_map = {"pending": "pending", "approved": "approved", "rejected": "rejected", "all": None}
    key = cq.data.split("_")[2]
    status = status_map.get(key)
    orders = await get_orders(status, limit=30)
    if not orders:
        await cq.answer("No orders found.", show_alert=True)
        return
    lines = []
    for o in orders:
        icon = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(o["status"], "•")
        lines.append(f"{icon} #{o['id']} | {o['category_name']} x{o['quantity']} | ₹{o['amount']:.0f} | uid:{o['user_id']}")
    await cq.message.answer(
        f"📦 *{key.title()} Orders:*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=back_kb("adm_orders"),
    )
    await cq.answer()


# Approve / Reject callbacks (sent from payment notification to admin)
@router.callback_query(F.data.startswith("approve_"))
@admin_only
async def cb_approve(cq: CallbackQuery, bot: Bot):
    order_id = int(cq.data.split("_")[1])
    order = await get_order(order_id)
    if not order:
        return await cq.answer("Order not found.", show_alert=True)
    if order["status"] != "pending":
        return await cq.answer(f"Already {order['status']}.", show_alert=True)

    # Deliver coupons
    codes = await fetch_and_mark_coupons(order["category_id"], order["quantity"], order_id, order["user_id"])
    if not codes:
        return await cq.answer("❌ Not enough stock! Approve manually after adding stock.", show_alert=True)

    await update_order_status(order_id, "approved", cq.from_user.id)

    # Notify user
    codes_text = "\n".join(f"`{c}`" for c in codes)
    try:
        await bot.send_message(
            order["user_id"],
            f"🎉 *Payment Approved!*\n\n"
            f"📦 Order #{order_id}\n"
            f"📁 {order['category_name']} × {order['quantity']}\n\n"
            f"🎟 *Your Coupons:*\n{codes_text}\n\n"
            f"Thank you for your purchase! 🙏",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Could not notify user %s: %s", order["user_id"], e)

    # Edit admin message
    await cq.message.edit_text(
        cq.message.text + f"\n\n✅ *Approved by* @{cq.from_user.username or cq.from_user.id}",
        parse_mode="Markdown",
    )
    await cq.answer("✅ Approved & delivered!", show_alert=True)


@router.callback_query(F.data.startswith("reject_"))
@admin_only
async def cb_reject(cq: CallbackQuery, bot: Bot):
    order_id = int(cq.data.split("_")[1])
    order = await get_order(order_id)
    if not order:
        return await cq.answer("Order not found.", show_alert=True)
    if order["status"] != "pending":
        return await cq.answer(f"Already {order['status']}.", show_alert=True)

    await update_order_status(order_id, "rejected", cq.from_user.id)

    # Refund if paid via wallet
    if order.get("paid_via") == "wallet":
        from database.db import update_wallet
        await update_wallet(order["user_id"], order["amount"])

    try:
        await bot.send_message(
            order["user_id"],
            f"❌ *Payment Rejected*\n\n"
            f"Order #{order_id} — {order['category_name']} × {order['quantity']}\n\n"
            f"If you believe this is an error, please contact support.\n"
            + ("💰 Your wallet has been refunded." if order.get("paid_via") == "wallet" else ""),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Could not notify user %s: %s", order["user_id"], e)

    await cq.message.edit_text(
        cq.message.text + f"\n\n❌ *Rejected by* @{cq.from_user.username or cq.from_user.id}",
        parse_mode="Markdown",
    )
    await cq.answer("❌ Rejected.", show_alert=True)


# ─────────────────────────── Statistics ──────────────────────────────────────

@router.callback_query(F.data == "adm_stats")
@admin_only
async def cb_stats(cq: CallbackQuery):
    stats = await get_sales_stats()
    await cq.message.edit_text(fmt_stats(stats), reply_markup=back_kb("adm_main"), parse_mode="Markdown")
    await cq.answer()


# ─────────────────────────── Users ───────────────────────────────────────────

@router.callback_query(F.data == "adm_users")
@admin_only
async def cb_users(cq: CallbackQuery):
    total = await get_user_count()
    await cq.message.edit_text(
        f"👥 *Total Users:* `{total}`\n\nCommands:\n/ban <user_id>\n/unban <user_id>\n/userinfo <user_id>",
        reply_markup=back_kb("adm_main"),
        parse_mode="Markdown",
    )
    await cq.answer()


@router.message(Command("ban"))
async def cmd_ban(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("Usage: /ban <user_id>")
    try:
        uid = int(parts[1])
        await ban_user(uid)
        await message.answer(f"🚫 User {uid} banned.")
    except Exception as e:
        await message.answer(f"Error: {e}")


@router.message(Command("unban"))
async def cmd_unban(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("Usage: /unban <user_id>")
    try:
        uid = int(parts[1])
        await unban_user(uid)
        await message.answer(f"✅ User {uid} unbanned.")
    except Exception as e:
        await message.answer(f"Error: {e}")


@router.message(Command("userinfo"))
async def cmd_userinfo(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("Usage: /userinfo <user_id>")
    try:
        uid = int(parts[1])
        user = await get_user(uid)
        if not user:
            return await message.answer("User not found.")
        await message.answer(
            f"👤 *User Info*\n"
            f"ID: `{user['user_id']}`\n"
            f"Name: {user['full_name']}\n"
            f"Username: @{user['username'] or 'N/A'}\n"
            f"Wallet: ₹{user['wallet']:.2f}\n"
            f"Referral Code: `{user['referral_code']}`\n"
            f"Referred by: `{user['referred_by'] or 'None'}`\n"
            f"Banned: {'Yes' if user['is_banned'] else 'No'}\n"
            f"Joined: {user['joined_at']}",
            parse_mode="Markdown",
        )
    except Exception as e:
        await message.answer(f"Error: {e}")


# ─────────────────────────── Settings ────────────────────────────────────────

@router.callback_query(F.data == "adm_settings")
@admin_only
async def cb_settings(cq: CallbackQuery):
    upi = await get_setting("upi_id", "Not set")
    channel = await get_setting("required_channel", "Not set")
    bonus = await get_setting("referral_bonus", "10")
    await cq.message.edit_text(
        f"⚙️ *Settings*\n\n"
        f"💳 UPI ID: `{upi}`\n"
        f"📢 Channel: `{channel}`\n"
        f"🎁 Referral Bonus: ₹`{bonus}`",
        reply_markup=admin_settings_kb(),
        parse_mode="Markdown",
    )
    await cq.answer()


@router.callback_query(F.data == "adm_set_upi")
@admin_only
async def cb_set_upi(cq: CallbackQuery, state: FSMContext):
    await cq.message.answer("💳 Send new *UPI ID*:", parse_mode="Markdown")
    await state.set_state(AdminSettingStates.waiting_upi)
    await cq.answer()


@router.message(AdminSettingStates.waiting_upi)
async def adm_set_upi(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await set_setting("upi_id", message.text.strip())
    await state.clear()
    await message.answer("✅ UPI ID updated.", reply_markup=admin_main_kb())


@router.callback_query(F.data == "adm_set_qr")
@admin_only
async def cb_set_qr(cq: CallbackQuery, state: FSMContext):
    await cq.message.answer("🖼 Send the *QR Code image*:", parse_mode="Markdown")
    await state.set_state(AdminSettingStates.waiting_qr)
    await cq.answer()


@router.message(AdminSettingStates.waiting_qr, F.photo)
async def adm_set_qr(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    path = f"qr_{photo.file_id}.jpg"
    await bot.download_file(file.file_path, destination=path)
    await set_setting("qr_path", path)
    await set_setting("qr_file_id", photo.file_id)
    await state.clear()
    await message.answer("✅ QR Code saved.", reply_markup=admin_main_kb())


@router.callback_query(F.data == "adm_set_channel")
@admin_only
async def cb_set_channel(cq: CallbackQuery, state: FSMContext):
    await cq.message.answer("📢 Send channel username (e.g. @mychannel):", parse_mode="Markdown")
    await state.set_state(AdminSettingStates.waiting_channel)
    await cq.answer()


@router.message(AdminSettingStates.waiting_channel)
async def adm_set_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await set_setting("required_channel", message.text.strip())
    await state.clear()
    await message.answer("✅ Channel updated.", reply_markup=admin_main_kb())


@router.callback_query(F.data == "adm_set_refbonus")
@admin_only
async def cb_set_refbonus(cq: CallbackQuery, state: FSMContext):
    await cq.message.answer("🎁 Send new referral bonus amount (e.g. 10):")
    await state.set_state(AdminSettingStates.waiting_refbonus)
    await cq.answer()


@router.message(AdminSettingStates.waiting_refbonus)
async def adm_set_refbonus(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        bonus = float(message.text.strip())
    except ValueError:
        return await message.answer("❌ Invalid amount.")
    await set_setting("referral_bonus", str(bonus))
    await state.clear()
    await message.answer(f"✅ Referral bonus set to ₹{bonus}.", reply_markup=admin_main_kb())


# ─────────────────────────── Broadcast ───────────────────────────────────────

@router.callback_query(F.data == "adm_broadcast")
@admin_only
async def cb_broadcast_start(cq: CallbackQuery, state: FSMContext):
    await cq.message.answer(
        "📣 Send the *broadcast message* (text, photo, or video).\n\n"
        "_Send /cancel to abort._",
        parse_mode="Markdown",
    )
    await state.set_state(AdminBroadcastStates.waiting_message)
    await cq.answer()


@router.message(AdminBroadcastStates.waiting_message)
async def adm_broadcast_msg(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text and message.text == "/cancel":
        await state.clear()
        return await message.answer("Broadcast cancelled.", reply_markup=admin_main_kb())

    users = await get_all_users()
    success = fail = 0
    prog = await message.answer(f"📣 Broadcasting to {len(users)} users...")

    for user in users:
        try:
            await message.copy_to(user["user_id"])
            success += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)  # Rate limit: ~20 msg/s

    await prog.edit_text(
        f"📣 *Broadcast complete!*\n✅ Sent: {success}\n❌ Failed: {fail}",
        parse_mode="Markdown",
    )
    await state.clear()
