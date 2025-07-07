"""Модуль для определения состояний конечных автоматов (FSM).

Этот файл содержит классы, наследуемые от `StatesGroup`, которые определяют
различные состояния для управления многошаговыми диалогами с пользователем.
Каждый класс представляет собой отдельный конечный автомат.
"""
from aiogram.fsm.state import State, StatesGroup


class SubscriptionStates(StatesGroup):
    """Состояния для конечного автомата (FSM) процесса подписки.

    Определяет шаги, через которые проходит пользователь при создании
    новой подписки на информационную рассылку.

    States:
        choosing_info_type: Пользователь выбирает тип информации
            (погода, новости, события).
        choosing_category: Пользователь выбирает категорию для новостей
            или событий.
        prompting_city_search: Пользователь вводит текст для поиска города.
        choosing_city_from_list: Пользователь выбирает город из
            предложенного списка.
        choosing_frequency: Пользователь выбирает частоту рассылки.
    """

    choosing_info_type = State()
    choosing_category = State()
    prompting_city_search = State()
    choosing_city_from_list = State()
    choosing_frequency = State()


class WeatherStates(StatesGroup):
    """Состояния для FSM одноразового запроса погоды.

    Используется, когда пользователь вызывает команду /weather без указания
    города, и бот должен дождаться его ввода.

    States:
        waiting_for_city: Бот ожидает, когда пользователь введет
            название города.
    """

    waiting_for_city = State()