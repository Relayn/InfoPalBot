import html
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from .constants import (
    INFO_TYPE_NEWS,
    INFO_TYPE_EVENTS,
    NEWS_CATEGORIES,
    EVENTS_CATEGORIES,
    INFO_TYPE_WEATHER,
    KUDAGO_LOCATION_SLUGS,
)


def get_frequency_keyboard() -> InlineKeyboardMarkup:
    """
    Создает и возвращает inline-клавиатуру для выбора частоты уведомлений.
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
        [InlineKeyboardButton(text="❌ Отмена", callback_data="subscribe_fsm_cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_city_selection_keyboard(cities: list[str]) -> InlineKeyboardMarkup:
    """
    Создает и возвращает inline-клавиатуру для выбора города из списка.

    Args:
        cities (list[str]): Список найденных городов.

    Returns:
        InlineKeyboardMarkup: Готовая клавиатура с городами.
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
        [InlineKeyboardButton(text="❌ Отмена", callback_data="subscribe_fsm_cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_profile_keyboard() -> InlineKeyboardMarkup:
    """
    Создает и возвращает inline-клавиатуру для главного меню профиля.
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
    """
    Создает и возвращает клавиатуру с одной кнопкой "Назад в профиль".
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
    subscriptions: list,
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру со списком подписок для управления.

    Args:
        subscriptions (list): Список объектов подписок.

    Returns:
        InlineKeyboardMarkup: Готовая клавиатура.
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
    """
    Создает и возвращает inline-клавиатуру для выбора категории новостей или событий.

    Args:
        info_type (str): Тип информации ('news' или 'events'), для которого
                         нужно сгенерировать клавиатуру.

    Returns:
        InlineKeyboardMarkup: Готовая клавиатура с категориями.
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
        [InlineKeyboardButton(text="❌ Отмена", callback_data="subscribe_fsm_cancel")]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)