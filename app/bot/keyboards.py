"""Модуль для создания и управления inline-клавиатурами.

Этот файл содержит функции-конструкторы, каждая из которых отвечает за
создание определенной inline-клавиатуры для различных этапов взаимодействия
с пользователем, таких как подписка, управление профилем и выбор опций.
"""
import html
from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.constants import (
    BTN_TEXT_CANCEL,
    CALLBACK_DATA_CANCEL_FSM,
    EVENTS_CATEGORIES,
    INFO_TYPE_EVENTS,
    INFO_TYPE_NEWS,
    INFO_TYPE_WEATHER,
    KUDAGO_LOCATION_SLUGS,
    NEWS_CATEGORIES,
)
from app.database.models import Subscription


def get_frequency_keyboard() -> InlineKeyboardMarkup:
    """Создает и возвращает inline-клавиатуру для выбора частоты уведомлений.

    Клавиатура предлагает интервальные варианты (каждые N часов) и один
    cron-вариант (ежедневно в 9:00 UTC), а также кнопку отмены.

    Returns:
        Готовая клавиатура для выбора частоты.
    """
    buttons = [
        [
            InlineKeyboardButton(text="Раз в 3 часа", callback_data="frequency:3"),
            InlineKeyboardButton(text="Раз в 6 часов", callback_data="frequency:6"),
        ],
        [
            InlineKeyboardButton(text="Раз в 12 часов", callback_data="frequency:12"),
            InlineKeyboardButton(text="Раз в 24 часа", callback_data="frequency:24"),
        ],
        [
            InlineKeyboardButton(
                text="Ежедневно в 9:00 (UTC)", callback_data="cron:09:00"
            )
        ],
        [
            InlineKeyboardButton(
                text=BTN_TEXT_CANCEL, callback_data=CALLBACK_DATA_CANCEL_FSM
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_city_selection_keyboard(cities: List[str]) -> InlineKeyboardMarkup:
    """Создает и возвращает inline-клавиатуру для выбора города из списка.

    Args:
        cities: Список найденных городов для отображения на кнопках.

    Returns:
        Готовая клавиатура с кнопками городов и кнопкой отмены.
    """
    buttons = []
    row = []
    for city in cities:
        row.append(
            InlineKeyboardButton(text=city, callback_data=f"city_select:{city}")
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append(
        [
            InlineKeyboardButton(
                text=BTN_TEXT_CANCEL, callback_data=CALLBACK_DATA_CANCEL_FSM
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_profile_keyboard() -> InlineKeyboardMarkup:
    """Создает и возвращает inline-клавиатуру для главного меню профиля.

    Returns:
        Готовая клавиатура с опциями "Управление подписками" и "Назад к боту".
    """
    buttons = [
        [
            InlineKeyboardButton(
                text="📜 Управление подписками", callback_data="profile_subscriptions"
            )
        ],
        [InlineKeyboardButton(text="⬅️ Назад к боту", callback_data="profile_close")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_to_profile_keyboard() -> InlineKeyboardMarkup:
    """Создает и возвращает клавиатуру с одной кнопкой "Назад в профиль".

    Используется в подменю профиля для возврата на главный экран.

    Returns:
        Готовая клавиатура с одной кнопкой.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад в профиль", callback_data="back_to_profile_menu"
                )
            ]
        ]
    )


def get_profile_subscriptions_keyboard(
    subscriptions: List[Subscription],
) -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком подписок для управления (удаления).

    Args:
        subscriptions: Список объектов подписок пользователя.

    Returns:
        Готовая клавиатура со списком подписок и кнопкой "Назад".
    """
    buttons = []
    for sub in subscriptions:
        schedule_str = ""
        if sub.frequency:
            schedule_str = f"раз в {sub.frequency} ч."
        elif sub.cron_expression:
            parts = sub.cron_expression.split()
            schedule_str = f"ежедневно в {int(parts[1]):02d}:{int(parts[0]):02d}"

        details_str = ""
        if sub.info_type == INFO_TYPE_WEATHER:
            details_str = f"🌦️ Погода: {html.escape(sub.details)}"
        elif sub.info_type == INFO_TYPE_NEWS:
            category_str = f" ({sub.category or 'все'})"
            details_str = f"📰 Новости{category_str}"
        elif sub.info_type == INFO_TYPE_EVENTS:
            city_name = next(
                (
                    name.capitalize()
                    for name, slug in KUDAGO_LOCATION_SLUGS.items()
                    if slug == sub.details
                ),
                sub.details,
            )
            category_str = f" ({sub.category or 'все'})"
            details_str = f"🎉 События: {html.escape(city_name)}{category_str}"

        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"❌ Удалить: {details_str} ({schedule_str})",
                    callback_data=f"profile_delete_sub:{sub.id}",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад в профиль", callback_data="back_to_profile_menu"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_categories_keyboard(info_type: str) -> InlineKeyboardMarkup:
    """Создает и возвращает inline-клавиатуру для выбора категории.

    Генерирует клавиатуру на основе типа информации (новости или события).

    Args:
        info_type: Тип информации ('news' или 'events'), для которого
            нужно сгенерировать клавиатуру.

    Returns:
        Готовая клавиатура с категориями и кнопкой отмены.
    """
    buttons = []
    categories_map = {}

    if info_type == INFO_TYPE_NEWS:
        categories_map = NEWS_CATEGORIES
    elif info_type == INFO_TYPE_EVENTS:
        categories_map = EVENTS_CATEGORIES

    if categories_map:
        row = []
        for slug, text in categories_map.items():
            row.append(
                InlineKeyboardButton(
                    text=text, callback_data=f"subscribe_category:{slug}"
                )
            )
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

    buttons.append(
        [
            InlineKeyboardButton(
                text="Без категории (все подряд)",
                callback_data="subscribe_category:any",
            )
        ]
    )
    buttons.append(
        [
            InlineKeyboardButton(
                text=BTN_TEXT_CANCEL, callback_data=CALLBACK_DATA_CANCEL_FSM
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)