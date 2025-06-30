from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from .constants import INFO_TYPE_NEWS, INFO_TYPE_EVENTS, NEWS_CATEGORIES, EVENTS_CATEGORIES

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
        # НОВАЯ КНОПКА
        [
            InlineKeyboardButton(
                text="Ежедневно в 9:00 (UTC)", callback_data="cron:09:00"
            )
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="subscribe_fsm_cancel")],
    ]
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
        # Создаем ряды по 2 кнопки в каждом для компактности
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
        if row:  # Добавляем оставшиеся кнопки, если их нечетное количество
            buttons.append(row)

    # Добавляем кнопку "Пропустить" для подписки на все категории
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