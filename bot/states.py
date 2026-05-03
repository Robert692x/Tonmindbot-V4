from aiogram.fsm.state import State, StatesGroup


class WalletStates(StatesGroup):
    waiting_for_address = State()


class AIStates(StatesGroup):
    chatting = State()


class PaymentStates(StatesGroup):
    awaiting_confirmation = State()


class PriceStates(StatesGroup):
    searching = State()


class TradeStates(StatesGroup):
    adding = State()


class WatchlistStates(StatesGroup):
    waiting_for_address = State()


class LeaderboardStates(StatesGroup):
    waiting_for_token_address = State()


class WalletManagerStates(StatesGroup):
    waiting_for_address = State()
    waiting_for_threshold = State()
    waiting_for_name = State()


class AdminStates(StatesGroup):
    waiting_for_note = State()
