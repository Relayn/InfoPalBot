"""Обработчики базовых команд бота.

Этот модуль содержит хендлеры для основных команд, таких как
/start, /help и /cancel. Эти команды составляют основу взаимодействия
пользователя с ботом.
"""
import logging
from typing import Optional

from aiogram import Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove

from app.database.crud import create_user_if_not_exists, log_user_action
from app.database.session import get_session

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel_any_state(message: types.Message, state: FSMContext):
    """Обрабатывает команду /cancel в любом состоянии FSM.

    Сбрасывает текущее состояние FSM, если оно установлено, и уведомляет
    пользователя об отмене действия. Если пользователь не находится ни в каком
    состоянии, сообщает, что отменять нечего.

    Args:
        message: Объект сообщения от пользователя.
        state: Контекст состояния FSM.
    """
    telegram_id: int = message.from_user.id
    current_state_str: Optional[str] = await state.get_state()
    log_details: str = f"State before cancel: {current_state_str}"

    with get_session() as db_session:
        log_user_action(db_session, telegram_id, "/cancel", log_details)

    if current_state_str is None:
        await message.answer(
            "Нет активного действия для отмены.", reply_markup=ReplyKeyboardRemove()
        )
        return

    logger.info(
        f"Пользователь {telegram_id} отменил действие командой /cancel "
        f"из состояния {current_state_str}."
    )
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=ReplyKeyboardRemove())


@router.message(Command("start"), StateFilter("*"))
async def process_start_command(message: types.Message, state: FSMContext):
    """Обрабатывает команду /start.

    Регистрирует пользователя, если он новый, сбрасывает любое активное
    состояние FSM и отправляет приветственное сообщение.

    Args:
        message: Объект сообщения от пользователя.
        state: Контекст состояния FSM.
    """
    telegram_id: int = message.from_user.id
    current_state = await state.get_state()
    logger.info(
        f"Команда /start вызвана пользователем {telegram_id}. "
        f"Текущее состояние: {current_state}"
    )
    if current_state:
        await state.clear()

    try:
        with get_session() as db_session:
            create_user_if_not_exists(session=db_session, telegram_id=telegram_id)
            log_user_action(
                db_session, telegram_id, "/start", "User started/restarted the bot"
            )

        await message.answer(
            f"Привет, {message.from_user.full_name}! Я InfoPalBot. "
            "Я могу предоставить тебе актуальную информацию.\n"
            "Используй /help, чтобы увидеть список доступных команд."
        )
    except Exception as e:
        logger.error(
            f"Ошибка при обработке /start для пользователя {telegram_id}: {e}",
            exc_info=True,
        )
        await message.answer(
            "Произошла ошибка при обработке вашего запроса. Попробуйте позже."
        )


@router.message(Command("help"))
async def process_help_command(message: types.Message):
    """Обрабатывает команду /help.

    Отправляет пользователю отформатированное сообщение со списком
    всех доступных команд и их кратким описанием.

    Args:
        message: Объект сообщения от пользователя.
    """
    telegram_id: int = message.from_user.id
    help_text: str = (
        "<b>Доступные команды:</b>\n\n"
        "/start - Перезапустить бота\n"
        "/profile - 👤 Мой профиль и подписки\n"
        "/weather <code>[город]</code> - ☀️ Узнать погоду\n"
        "/news - 📰 Последние новости (США)\n"
        "/events <code>[город]</code> - 🎉 События в городе\n\n"
        "<b>Управление подписками:</b>\n"
        "/subscribe - 🔔 Подписаться на рассылку\n"
        "/mysubscriptions - 📜 Посмотреть мои подписки\n"
        "/unsubscribe - 🔕 Отписаться от рассылки\n\n"
        "/cancel - ❌ Отменить текущее действие\n"
        "/help - ❓ Показать эту справку"
    )
    await message.answer(help_text)
    logger.info(f"Отправлена справка по команде /help пользователю {telegram_id}")
    with get_session() as db_session:
        log_user_action(db_session, telegram_id, "/help")