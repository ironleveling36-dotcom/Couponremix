"""
main.py — Bot entry point (aiogram v3).

Crash strategy:
  • Any unhandled exception → log it, notify admins, exit with code 1
  • Railway (restartPolicyType=ON_FAILURE) restarts the container automatically
  • This avoids the "Router is already attached" error that happens when you
    try to reuse module-level router singletons inside a supervisor loop.
"""

import asyncio
import logging
import sys
import traceback
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery

from config import BOT_TOKEN, ADMIN_IDS
from database.db import init_db

# ─── Routers (module-level singletons — created once per process, that's fine) ─
from handlers.admin import router as admin_router
from handlers.user import router as user_router
from handlers.payment import router as payment_router
from handlers.wallet import router as wallet_router, handle_wallet_topup_approval, WALLET_TOPUP_CATEGORY
from handlers.referral import router as referral_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ─────────────────────────── Admin crash notifier ────────────────────────────

async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="Markdown")
        except Exception:
            pass


# ─────────────────────────── Dispatcher setup ────────────────────────────────

def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Wallet top-up hook — must be registered BEFORE admin_router.
    # Created fresh here so the function can be called multiple times safely
    # (e.g. in tests) without hitting "Router already attached" errors.
    wallet_hook = Router()

    @wallet_hook.callback_query(F.data.startswith("approve_"))
    async def _approve_wallet_hook(cq: CallbackQuery, bot: Bot):
        """
        Intercepts approve_ callbacks before admin.py.
        Wallet top-up orders are handled here; shop orders fall through.
        """
        order_id = int(cq.data.split("_")[1])
        from database.db import get_order
        order = await get_order(order_id)
        if order and order.get("category_name") == WALLET_TOPUP_CATEGORY:
            if order["status"] != "pending":
                return await cq.answer(f"Already {order['status']}.", show_alert=True)
            await handle_wallet_topup_approval(bot, order, cq.from_user.id)
            try:
                await cq.message.edit_text(
                    cq.message.text + f"\n\n✅ *Wallet credited* — approved by "
                    f"@{cq.from_user.username or cq.from_user.id}",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            await cq.answer("✅ Wallet credited!", show_alert=True)
        # Fall through to admin_router for normal orders

    dp.include_router(wallet_hook)
    dp.include_router(admin_router)
    dp.include_router(user_router)
    dp.include_router(payment_router)
    dp.include_router(wallet_router)
    dp.include_router(referral_router)
    return dp


# ─────────────────────────── Lifecycle hooks ─────────────────────────────────

async def on_startup(bot: Bot) -> None:
    await init_db()
    me = await bot.get_me()
    logger.info("Bot @%s started (id=%s).", me.username, me.id)
    await notify_admins(
        bot,
        f"✅ *Bot started* — @{me.username}\n"
        f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
    )


async def on_shutdown(bot: Bot) -> None:
    logger.info("Bot shutting down.")


# ─────────────────────────── Main ────────────────────────────────────────────

async def main() -> None:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        tb = traceback.format_exc()
        logger.critical("Fatal error:\n%s", tb)
        # Notify admins then exit — Railway will restart the container
        try:
            await notify_admins(
                bot,
                f"💥 *Bot crashed — restarting*\n\n"
                f"`{type(e).__name__}: {e}`\n\n"
                f"```\n{tb[-1800:]}\n```",
            )
        except Exception:
            pass
        await bot.session.close()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
