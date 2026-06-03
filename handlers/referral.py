"""
handlers/referral.py — Referral system.

Each user gets a unique referral code.
Sharing the link: https://t.me/<BOT_USERNAME>?start=ref_<code>
When a new user starts via that link:
  • Referrer gets wallet credit (configurable via admin)
  • Record is saved to prevent double-counting
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

from database.db import get_user, get_setting
from utils.keyboards import back_kb
from config import BOT_USERNAME, REFERRAL_BONUS, CURRENCY_SYMBOL

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "referral")
async def cb_referral(cq: CallbackQuery):
    user = await get_user(cq.from_user.id)
    if not user:
        return await cq.answer("Something went wrong.", show_alert=True)

    code = user["referral_code"]
    bot_username = await get_setting("bot_username", BOT_USERNAME)
    bonus = await get_setting("referral_bonus", str(REFERRAL_BONUS))

    if bot_username:
        link = f"https://t.me/{bot_username}?start=ref_{code}"
        link_text = f"\n🔗 Your referral link:\n`{link}`"
    else:
        link_text = f"\n🔑 Your referral code: `ref_{code}`\n_(Set BOT_USERNAME in env for full link)_"

    await cq.message.edit_text(
        f"🎁 *Referral Program*\n\n"
        f"Earn *{CURRENCY_SYMBOL}{float(bonus):.0f}* wallet credit for every new user you refer!\n"
        f"{link_text}\n\n"
        f"Share this link with friends. When they start the bot, you both benefit!\n\n"
        f"💰 Your wallet: *{CURRENCY_SYMBOL}{user['wallet']:.2f}*",
        reply_markup=back_kb("main_menu"),
        parse_mode="Markdown",
    )
    await cq.answer()
