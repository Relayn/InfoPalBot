# Файл: app/bot/fsm.py

from aiogram.fsm.state import State, StatesGroup


class SubscriptionStates(StatesGroup):
    """
    Состояния для конечного автомата (FSM) управления процессом подписки пользователя.
    """
    choosing_info_type = State()
    entering_city_weather = State()
    entering_city_events = State()
    choosing_frequency = State()