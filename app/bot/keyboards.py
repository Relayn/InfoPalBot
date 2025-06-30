# Файл: app/bot/keyboards.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


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