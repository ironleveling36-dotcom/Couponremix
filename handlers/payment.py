"""
handlers/payment.py — Payment flow.

UPI payment → admin notification → approve/reject (in admin.py)
Wallet payment → instant approval
"""

import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import (
    get_order, get_user, update_order_status,
    fetch_and_mark_coupons, update_wallet, get_setting,
)
from utils.keyboards import admin_approve_kb, back_kb
from config import ADMIN_IDS, CURRENCY_SYMBOL

router = Router()
logger = logging.getLogger(__name__)


async def _notify_admins(bot: Bot, order: dict):
    """Send payment approval request to all admins."""
    user = await get_user(order["user_id"])
    uname = f"@{user['username']}" if user and user.get("username") else str(order["user_id"])
    text = (
        f"💳 *New Payment Request*\n\n"
        f"🆔 Order: #{order['id']}\n"
        f"👤 User: {uname} (ID: `{order['user_id']}`)\n"
        f"📁 Category: {order['category_name']}\n"
        f"📦 Quantity: {order['quantity']}\n"
        f"💰 Amount: {CURRENCY_SYMBOL}{order['amount']:.2f}\n"
        f"💳 Method: UPI"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                text,
                reply_markup=admin_approve_kb(order["id"]),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning("Could not notify admin %s: %s", admin_id, e)


@router.callback_query(F.data.startswith("paid_upi_"))
async def cb_paid_upi(cq: CallbackQuery, bot: Bot, state: FSMContext):
    order_id = int(cq.data.split("_")[2])
    order = await get_order(order_id)

    if not order or order["user_id"] != cq.from_user.id:
        return await cq.answer("❌ Order not found.", show_alert=True)
    if order["status"] != "pending":
        return await cq.answer(f"This order is already {order['status']}.", show_alert=True)

    await _notify_admins(bot, order)

    await cq.message.edit_text(
        f"✅ *Payment request sent!*\n\n"
        f"Order #{order_id} is under review.\n"
        f"You'll be notified once approved.\n\n"
        f"⏳ Usually approved within a few minutes.",
        reply_markup=back_kb("main_menu"),
        parse_mode="Markdown",
    )
    await state.clear()
    await cq.answer("Payment request submitted!")


@router.callback_query(F.data.startswith("paid_wallet_"))
async def cb_paid_wallet(cq: CallbackQuery, bot: Bot, state: FSMContext):
    order_id = int(cq.data.split("_")[2])
    order = await get_order(order_id)

    if not order or order["user_id"] != cq.from_user.id:
        return await cq.answer("❌ Order not found.", show_alert=True)
    if order["status"] != "pending":
        return await cq.answer(f"Already {order['status']}.", show_alert=True)

    # Check wallet balance
    user = await get_user(cq.from_user.id)
    if not user or user["wallet"] < order["amount"]:
        return await cq.answer("❌ Insufficient wallet balance!", show_alert=True)

    # Deduct wallet
    new_balance = await update_wallet(cq.from_user.id, -order["amount"])

    # Update order payment method
    from database.db import DB_PATH
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET paid_via='wallet' WHERE id=?", (order_id,))
        await db.commit()

    # Deliver coupons immediately
    codes = await fetch_and_mark_coupons(order["category_id"], order["quantity"], order_id, cq.from_user.id)
    if not codes:
        # Refund and abort
        await update_wallet(cq.from_user.id, order["amount"])
        return await cq.answer("❌ Out of stock! Wallet refunded.", show_alert=True)

    await update_order_status(order_id, "approved", 0)

    codes_text = "\n".join(f"`{c}`" for c in codes)
    await cq.message.edit_text(
        f"🎉 *Purchase Successful!*\n\n"
        f"📁 {order['category_name']} × {order['quantity']}\n"
        f"💰 Paid: {CURRENCY_SYMBOL}{order['amount']:.2f} (Wallet)\n"
        f"💳 Remaining Balance: {CURRENCY_SYMBOL}{new_balance:.2f}\n\n"
        f"🎟 *Your Coupons:*\n{codes_text}",
        reply_markup=back_kb("main_menu"),
        parse_mode="Markdown",
    )
    await state.clear()
    await cq.answer("✅ Purchase complete!")

    # Notify admins of wallet sale
    user_info = await get_user(cq.from_user.id)
    uname = f"@{user_info['username']}" if user_info and user_info.get("username") else str(cq.from_user.id)
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 *Wallet Sale*\n\n"
                f"👤 {uname}\n"
                f"📁 {order['category_name']} × {order['quantity']}\n"
                f"💰 {CURRENCY_SYMBOL}{order['amount']:.2f} (auto-approved)",
                parse_mode="Markdown",
            )
        except Exception:
            pass
