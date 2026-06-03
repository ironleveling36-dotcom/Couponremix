"""
handlers/user.py — User-facing flows.

/start → channel check → main menu
Shop: browse categories → pick qty → payment page
My Orders
Referral info
"""

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart

from database.db import (
    get_categories, get_category, create_order,
    get_user, get_user_orders, get_user_by_referral,
    record_referral, credit_referral_bonus, get_setting,
)
from utils.keyboards import (
    join_channel_kb, main_menu_kb, categories_kb,
    quantity_kb, payment_kb, back_kb,
)
from utils.helpers import is_subscribed, ensure_user, fmt_order
from utils.states import ShopStates
from config import CURRENCY_SYMBOL, BOT_USERNAME, REFERRAL_BONUS

router = Router()
logger = logging.getLogger(__name__)


# ─────────────────────────── /start ──────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    await ensure_user(message)

    user = message.from_user
    args = message.text.split()
    ref_code = args[1] if len(args) > 1 else None

    # Handle referral
    if ref_code and ref_code.startswith("ref_"):
        code = ref_code[4:]
        referrer = await get_user_by_referral(code)
        if referrer and referrer["user_id"] != user.id:
            new = await record_referral(referrer["user_id"], user.id)
            if new:
                bonus = float(await get_setting("referral_bonus", str(REFERRAL_BONUS)))
                await credit_referral_bonus(referrer["user_id"], user.id, bonus)
                try:
                    await bot.send_message(
                        referrer["user_id"],
                        f"🎉 *Referral Bonus!*\nUser @{user.username or user.id} joined via your link.\n"
                        f"💰 +₹{bonus:.2f} added to your wallet!",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

    # Channel gate check
    subscribed = await is_subscribed(bot, user.id)
    channel = await get_setting("required_channel", "")

    if not subscribed and channel:
        return await message.answer(
            f"👋 Welcome, *{user.first_name}*!\n\n"
            f"To use this bot, you must join our channel first:",
            reply_markup=join_channel_kb(channel),
            parse_mode="Markdown",
        )

    await show_main_menu(message)


async def show_main_menu(message: Message):
    db_user = await get_user(message.from_user.id)
    wallet = db_user["wallet"] if db_user else 0.0
    await message.answer(
        f"🏠 *Main Menu*\n\n"
        f"Welcome back, *{message.from_user.first_name}*! 👋\n"
        f"💰 Wallet Balance: *{CURRENCY_SYMBOL}{wallet:.2f}*",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(cq: CallbackQuery, bot: Bot):
    subscribed = await is_subscribed(bot, cq.from_user.id)
    channel = await get_setting("required_channel", "")
    if not subscribed and channel:
        await cq.answer("Please join the channel first!", show_alert=True)
        return
    db_user = await get_user(cq.from_user.id)
    wallet = db_user["wallet"] if db_user else 0.0
    await cq.message.edit_text(
        f"🏠 *Main Menu*\n\n💰 Wallet Balance: *{CURRENCY_SYMBOL}{wallet:.2f}*",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown",
    )
    await cq.answer()


# ─────────────────────────── Channel verify ──────────────────────────────────

@router.callback_query(F.data == "verify_join")
async def cb_verify(cq: CallbackQuery, bot: Bot):
    subscribed = await is_subscribed(bot, cq.from_user.id)
    if subscribed:
        await cq.answer("✅ Verified!", show_alert=False)
        db_user = await get_user(cq.from_user.id)
        wallet = db_user["wallet"] if db_user else 0.0
        await cq.message.edit_text(
            f"🏠 *Main Menu*\n\n💰 Wallet: *{CURRENCY_SYMBOL}{wallet:.2f}*",
            reply_markup=main_menu_kb(),
            parse_mode="Markdown",
        )
    else:
        await cq.answer("❌ You haven't joined yet. Please join and try again.", show_alert=True)


# ─────────────────────────── Shop ────────────────────────────────────────────

@router.callback_query(F.data == "shop")
async def cb_shop(cq: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    subscribed = await is_subscribed(bot, cq.from_user.id)
    channel = await get_setting("required_channel", "")
    if not subscribed and channel:
        return await cq.answer("Please join our channel first!", show_alert=True)

    cats = await get_categories(active_only=True)
    if not cats:
        return await cq.message.edit_text(
            "🛒 No products available right now. Check back soon!",
            reply_markup=back_kb("main_menu"),
        )

    await cq.message.edit_text(
        "🛒 *Choose a Category:*\n\n_(🟢 = in stock | 🔴 = out of stock)_",
        reply_markup=categories_kb(cats),
        parse_mode="Markdown",
    )
    await cq.answer()


@router.callback_query(F.data.startswith("cat_"))
async def cb_cat_select(cq: CallbackQuery, state: FSMContext):
    cat_id = int(cq.data.split("_")[1])
    cat = await get_category(cat_id)
    if not cat:
        return await cq.answer("Category not found.", show_alert=True)
    if cat["stock"] == 0:
        return await cq.answer("❌ Out of stock!", show_alert=True)

    await state.update_data(
        cat_id=cat_id,
        cat_name=cat["name"],
        price=cat["price"],
        stock=cat["stock"],
        user_id=cq.from_user.id,   # store explicitly — cq.message has no from_user
    )
    await cq.message.edit_text(
        f"📁 *{cat['name']}*\n"
        f"💰 Price: {CURRENCY_SYMBOL}{cat['price']:.2f}/unit\n"
        f"📦 Available: {cat['stock']} units\n\n"
        f"Select quantity:",
        reply_markup=quantity_kb(cat_id, cat["stock"]),
        parse_mode="Markdown",
    )
    await state.set_state(ShopStates.selecting_category)
    await cq.answer()


@router.callback_query(F.data.startswith("qty_custom_"))
async def cb_qty_custom(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await cq.message.answer(
        f"✏️ Enter quantity (1–{data.get('stock', 99)}):",
        reply_markup=back_kb("shop"),
    )
    await state.set_state(ShopStates.entering_quantity)
    await cq.answer()


@router.message(ShopStates.entering_quantity)
async def msg_qty_custom(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    try:
        qty = int(message.text.strip())
        if qty < 1 or qty > data.get("stock", 9999):
            raise ValueError
    except ValueError:
        return await message.answer(
            f"❌ Enter a valid number between 1 and {data.get('stock', 9999)}."
        )
    # user_id stored in state from cb_cat_select
    user_id = data.get("user_id", message.from_user.id)
    await _show_payment_page(message, bot, data, qty, user_id, edit=False)
    await state.set_state(ShopStates.on_payment_page)


# Must come AFTER qty_custom_ handler to avoid prefix collision
@router.callback_query(F.data.regexp(r"^qty_\d+_\d+$"))
async def cb_qty_select(cq: CallbackQuery, state: FSMContext, bot: Bot):
    # Format: qty_<cat_id>_<qty>
    parts = cq.data.split("_")
    qty = int(parts[2])
    data = await state.get_data()
    user_id = data.get("user_id", cq.from_user.id)
    await _show_payment_page(cq.message, bot, data, qty, user_id, edit=True)
    await state.set_state(ShopStates.on_payment_page)
    await cq.answer()


async def _show_payment_page(
    target: Message,
    bot: Bot,
    data: dict,
    qty: int,
    user_id: int,
    edit: bool = False,
):
    cat = await get_category(data["cat_id"])
    if not cat or cat["stock"] < qty:
        msg = "❌ Not enough stock."
        if edit:
            await target.edit_text(msg)
        else:
            await target.answer(msg)
        return

    total = round(cat["price"] * qty, 2)
    upi = await get_setting("upi_id", "Not configured")
    qr_file_id = await get_setting("qr_file_id", "")

    db_user = await get_user(user_id)
    wallet = db_user["wallet"] if db_user else 0.0

    order_id = await create_order(user_id, data["cat_id"], cat["name"], qty, total, paid_via="upi")

    text = (
        f"💳 *Payment Page*\n\n"
        f"📁 {cat['name']} × {qty}\n"
        f"💰 Total: *{CURRENCY_SYMBOL}{total:.2f}*\n\n"
        f"🏦 UPI ID: `{upi}`\n"
        f"_Pay the exact amount and click 'I Have Paid'_"
    )

    kb = payment_kb(order_id, has_wallet=wallet > 0, wallet_enough=wallet >= total)

    if qr_file_id:
        # Can't edit a text message into a photo — always send new
        if edit:
            try:
                await target.delete()
            except Exception:
                pass
        await bot.send_photo(
            user_id, qr_file_id, caption=text, reply_markup=kb, parse_mode="Markdown"
        )
    else:
        if edit:
            await target.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        else:
            await target.answer(text, reply_markup=kb, parse_mode="Markdown")


# ─────────────────────────── My Orders ───────────────────────────────────────

@router.callback_query(F.data == "my_orders")
async def cb_my_orders(cq: CallbackQuery):
    orders = await get_user_orders(cq.from_user.id)
    if not orders:
        return await cq.message.edit_text(
            "📦 You have no orders yet.",
            reply_markup=back_kb("main_menu"),
        )
    lines = []
    for o in orders:
        icon = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(o["status"], "•")
        lines.append(
            f"{icon} #{o['id']} — {o['category_name']} ×{o['quantity']}"
            f" — {CURRENCY_SYMBOL}{o['amount']:.0f} [{o['status']}]"
        )
    await cq.message.edit_text(
        "📦 *Your Orders:*\n\n" + "\n".join(lines),
        reply_markup=back_kb("main_menu"),
        parse_mode="Markdown",
    )
    await cq.answer()


# ─────────────────────────── Cancel order ────────────────────────────────────

@router.callback_query(F.data.startswith("cancel_order_"))
async def cb_cancel_order(cq: CallbackQuery, state: FSMContext):
    from database.db import update_order_status
    order_id = int(cq.data.split("_")[2])
    await update_order_status(order_id, "rejected", cq.from_user.id)
    await state.clear()
    await cq.message.edit_text("❌ Order cancelled.", reply_markup=back_kb("main_menu"))
    await cq.answer("Order cancelled.")
