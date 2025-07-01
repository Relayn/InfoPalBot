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
    """
    Обрабатывает команду /cancel в любом состоянии FSM (или без него).

    Сбрасывает текущее состояние FSM, если оно установлено, и уведомляет
    пользователя об отмене действия.

    Args:
        message (types.Message): Объект сообщения от пользователя.
        state (FSMContext): Контекст состояния FSM.
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
        f"Пользователь {telegram_id} отменил действие командой /cancel из состояния {current_state_str}."
    )
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=ReplyKeyboardRemove())


@router.message(Command("start"), StateFilter("*"))
async def process_start_command(message: types.Message, state: FSMContext):
    """
    Обрабатывает команду /start.

    Регистрирует пользователя, если он новый, сбрасывает любое активное
    состояние FSM и отправляет приветственное сообщение.

    Args:
        message (types.Message): Объект сообщения от пользователя.
        state (FSMContext): Контекст состояния FSM.
    """
    telegram_id: int = message.from_user.id
    logger.info(
        f"Команда /start вызвана пользователем {telegram_id}. Текущее состояние: {await state.get_state()}"
    )
    await state.clear()

    log_command: str = "/start"
    log_details: Optional[str] = "User started/restarted the bot"

    try:
        with get_session() as db_session:
            create_user_if_not_exists(session=db_session, telegram_id=telegram_id)
            log_user_action(db_session, telegram_id, log_command, log_details)

        await message.answer(
            f"Привет, {message.from_user.full_name}! Я InfoPalBot. "
            f"Я могу предоставить тебе актуальную информацию.\n"
            f"Используй /help, чтобы увидеть список доступных команд."
        )
    except Exception as e:
        logger.error(
            f"Ошибка при обработке команды /start для пользователя {telegram_id}: {e}",
            exc_info=True,
        )
        await message.answer(
            "Произошла ошибка при обработке вашего запроса. Попробуйте позже."
        )


@router.message(Command("help"))
async def process_help_command(message: types.Message):
    """
    Обрабатывает команду /help, отправляя пользователю список доступных команд.

    Args:
        message (types.Message): Объект сообщения от пользователя.
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