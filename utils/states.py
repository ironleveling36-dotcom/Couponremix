"""
utils/states.py — FSM state groups.
"""

from aiogram.fsm.state import State, StatesGroup


class AdminCategoryStates(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_desc = State()
    # Edit
    edit_name = State()
    edit_price = State()
    edit_desc = State()


class AdminCouponStates(StatesGroup):
    waiting_codes = State()   # paste codes, one per line


class AdminSettingStates(StatesGroup):
    waiting_upi = State()
    waiting_qr = State()
    waiting_channel = State()
    waiting_refbonus = State()


class AdminBroadcastStates(StatesGroup):
    waiting_message = State()
    confirm = State()


class ShopStates(StatesGroup):
    selecting_category = State()
    entering_quantity = State()
    on_payment_page = State()


class WalletStates(StatesGroup):
    entering_amount = State()
    on_payment_page = State()
