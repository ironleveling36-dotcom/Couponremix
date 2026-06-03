"""
handlers/wallet.py — Wallet top-up and balance management.

Flow:
  User → "Wallet" menu → sees balance + top-up options
  Selects amount → payment page (UPI + QR)
  "I Have Paid" → admin notification (approve = credits wallet)
  Admin approves → wallet balance updated, user notified
"""

import logging
import aiosqlite
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from database.db import (
    get_user, get_order, update_wallet, create_order,
    get_setting, DB_PATH, update_order_status,
)
from utils.keyboards import wallet_topup_kb, payment_kb, back_kb, admin_approve_kb
from utils.states import WalletStates
from config import ADMIN_IDS, CURRENCY_SYMBOL

router = Router()
logger = logging.getLogger(__name__)

WALLET_TOPUP_CATEGORY = "__wallet_topup__"


@router.callback_query(F.data == "wallet")
async def cb_wallet(cq: CallbackQuery):
    user = await get_user(cq.from_user.id)
    balance = user["wallet"] if user else 0.0
    await cq.message.edit_text(
        f"💰 *Your Wallet*\n\n"
        f"Balance: *{CURRENCY_SYMBOL}{balance:.2f}*\n\n"
        f"Add money to your wallet for instant purchases!",
        reply_markup=wallet_topup_kb(),
        parse_mode="Markdown",
    )
    await cq.answer()


@router.callback_query(F.data.startswith("topup_") & ~F.data.startswith("topup_custom"))
async def cb_topup_amount(cq: CallbackQuery, bot: Bot, state: FSMContext):
    amount = float(cq.data.split("_")[1])
    await _start_wallet_topup(cq, bot, state, amount)


@router.callback_query(F.data == "topup_custom")
async def cb_topup_custom(cq: CallbackQuery, state: FSMContext):
    await cq.message.answer("💰 Enter amount to add to wallet (min ₹10):")
    await state.set_state(WalletStates.entering_amount)
    await cq.answer()


@router.message(WalletStates.entering_amount)
async def msg_topup_amount(message: Message, bot: Bot, state: FSMContext):
    try:
        amount = float(message.text.strip())
        if amount < 10:
            raise ValueError
    except ValueError:
        return await message.answer("❌ Please enter a valid amount (minimum ₹10).")
    await _start_wallet_topup_msg(message, bot, state, amount)


async def _start_wallet_topup(cq: CallbackQuery, bot: Bot, state: FSMContext, amount: float):
    upi = await get_setting("upi_id", "Not configured")
    qr_file_id = await get_setting("qr_file_id", "")

    # Create a special wallet top-up order
    order_id = await create_order(cq.from_user.id, 0, WALLET_TOPUP_CATEGORY, 1, amount, paid_via="upi")

    text = (
        f"💳 *Wallet Top-up*\n\n"
        f"Amount: *{CURRENCY_SYMBOL}{amount:.2f}*\n\n"
        f"🏦 UPI ID: `{upi}`\n"
        f"_Pay exactly {CURRENCY_SYMBOL}{amount:.2f} and click 'I Have Paid'_"
    )
    kb = payment_kb(order_id, has_wallet=False)

    await state.set_state(WalletStates.on_payment_page)
    await state.update_data(order_id=order_id, amount=amount)

    if qr_file_id:
        await bot.send_photo(cq.from_user.id, qr_file_id, caption=text, reply_markup=kb, parse_mode="Markdown")
        await cq.message.delete()
    else:
        await cq.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await cq.answer()


async def _start_wallet_topup_msg(message: Message, bot: Bot, state: FSMContext, amount: float):
    upi = await get_setting("upi_id", "Not configured")
    qr_file_id = await get_setting("qr_file_id", "")
    order_id = await create_order(message.from_user.id, 0, WALLET_TOPUP_CATEGORY, 1, amount, paid_via="upi")

    text = (
        f"💳 *Wallet Top-up*\n\n"
        f"Amount: *{CURRENCY_SYMBOL}{amount:.2f}*\n\n"
        f"🏦 UPI ID: `{upi}`\n"
        f"_Pay exactly {CURRENCY_SYMBOL}{amount:.2f} and click 'I Have Paid'_"
    )
    kb = payment_kb(order_id, has_wallet=False)
    await state.set_state(WalletStates.on_payment_page)
    await state.update_data(order_id=order_id, amount=amount)

    if qr_file_id:
        await bot.send_photo(message.from_user.id, qr_file_id, caption=text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")


# ─────────────────────────── Admin approves wallet topup ──────────────────────
# This is wired in admin.py via approve_/reject_ handlers.
# We hook into the approve flow by detecting wallet orders.

async def handle_wallet_topup_approval(bot: Bot, order: dict, admin_id: int):
    """Called from admin approve handler when order is a wallet top-up."""
    new_balance = await update_wallet(order["user_id"], order["amount"])
    await update_order_status(order["id"], "approved", admin_id)
    try:
        await bot.send_message(
            order["user_id"],
            f"✅ *Wallet Topped Up!*\n\n"
            f"💰 Added: {CURRENCY_SYMBOL}{order['amount']:.2f}\n"
            f"💳 New Balance: {CURRENCY_SYMBOL}{new_balance:.2f}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Could not notify user %s: %s", order["user_id"], e)
