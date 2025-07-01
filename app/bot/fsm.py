from aiogram.fsm.state import State, StatesGroup


class SubscriptionStates(StatesGroup):
    """
    Состояния для конечного автомата (FSM) управления процессом подписки пользователя.
    """
    choosing_info_type = State()
    choosing_category = State()

    # Новые состояния для пошагового выбора города
    prompting_city_search = State()
    choosing_city_from_list = State()

    choosing_frequency = State()