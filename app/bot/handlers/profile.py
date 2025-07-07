"""Обработчики для раздела "Профиль" (личный кабинет пользователя).

Этот модуль содержит хендлеры для команды /profile и связанных с ней
inline-кнопок. Он реализует функционал личного кабинета, где пользователь
может просматривать свои подписки и управлять ими (в частности, удалять).
"""
import logging

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command

from app.bot.keyboards import (
    get_back_to_profile_keyboard,
    get_profile_keyboard,
    get_profile_subscriptions_keyboard,
)
from app.database.crud import (
    delete_subscription as db_delete_subscription,
)
from app.database.crud import get_subscriptions_by_user_id, get_user_by_telegram_id
from app.database.crud import log_user_action
from app.database.models import Subscription
from app.database.session import get_session
from app.scheduler.main import scheduler

logger = logging.getLogger(__name__)
router = Router()


async def show_profile_menu(message: types.Message, log_text: str):
    """Отображает главное меню профиля, редактируя существующее сообщение.

    Args:
        message: Объект сообщения для редактирования.
        log_text: Текст для записи в лог действия.
    """
    telegram_id = message.from_user.id
    with get_session() as db_session:
        log_user_action(db_session, telegram_id, "/profile", log_text)

    try:
        await message.edit_text(
            "Добро пожаловать в ваш профиль! "
            "Здесь вы можете управлять своими подписками.",
            reply_markup=get_profile_keyboard(),
        )
    except TelegramBadRequest:
        logger.warning("Не удалось отредактировать сообщение в show_profile_menu.")


@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    """Обрабатывает команду /profile, открывая меню личного кабинета.

    Args:
        message: Объект сообщения от пользователя.
    """
    telegram_id = message.from_user.id
    with get_session() as db_session:
        log_user_action(db_session, telegram_id, "/profile", "Opened profile menu")

    await message.answer(
        "Добро пожаловать в ваш профиль! "
        "Здесь вы можете управлять своими подписками.",
        reply_markup=get_profile_keyboard(),
    )


@router.callback_query(F.data == "back_to_profile_menu")
async def cq_back_to_profile_menu(callback_query: types.CallbackQuery):
    """Обрабатывает нажатие кнопки 'Назад в профиль'.

    Args:
        callback_query: Объект callback-запроса от пользователя.
    """
    await callback_query.answer()
    await show_profile_menu(callback_query.message, "Returned to profile menu")


@router.callback_query(F.data == "profile_close")
async def cq_profile_close(callback_query: types.CallbackQuery):
    """Обрабатывает кнопку 'Назад к боту', закрывая меню профиля.

    Args:
        callback_query: Объект callback-запроса от пользователя.
    """
    await callback_query.answer("Закрываю меню...")
    try:
        await callback_query.message.delete()
    except TelegramBadRequest:
        logger.info("Не удалось удалить сообщение, возможно, оно уже удалено.")


@router.callback_query(F.data == "profile_subscriptions")
async def cq_profile_subscriptions(callback_query: types.CallbackQuery):
    """Отображает список подписок пользователя для управления.

    Args:
        callback_query: Объект callback-запроса от пользователя.
    """
    await callback_query.answer()
    telegram_id = callback_query.from_user.id

    with get_session() as db_session:
        user = get_user_by_telegram_id(db_session, telegram_id)
        if not user:
            await callback_query.message.edit_text("Не удалось найти ваш профиль.")
            return

        subscriptions = get_subscriptions_by_user_id(db_session, user.id)
        if not subscriptions:
            await callback_query.message.edit_text(
                "У вас нет активных подписок.",
                reply_markup=get_back_to_profile_keyboard(),
            )
            return

        await callback_query.message.edit_text(
            "Нажмите на подписку, чтобы удалить ее:",
            reply_markup=get_profile_subscriptions_keyboard(subscriptions),
        )


@router.callback_query(F.data.startswith("profile_delete_sub:"))
async def cq_profile_delete_sub(callback_query: types.CallbackQuery):
    """Удаляет выбранную подписку и обновляет список.

    Args:
        callback_query: Объект callback-запроса от пользователя.
            Ожидается, что `data` будет в формате 'profile_delete_sub:<id>'.
    """
    await callback_query.answer("Удаляю подписку...")
    sub_id_to_delete = int(callback_query.data.split(":")[1])
    telegram_id = callback_query.from_user.id

    with get_session() as db_session:
        user = get_user_by_telegram_id(db_session, telegram_id)
        if not user:
            await callback_query.message.edit_text("Ошибка: ваш профиль не найден.")
            return

        sub_to_delete = db_session.get(Subscription, sub_id_to_delete)
        if not sub_to_delete or sub_to_delete.user_id != user.id:
            await callback_query.answer("Ошибка: подписка не найдена.", show_alert=True)
            return

        db_delete_subscription(db_session, sub_id_to_delete)
        job_id = f"sub_{sub_id_to_delete}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f"Задача {job_id} удалена из планировщика через профиль.")

        remaining_subscriptions = get_subscriptions_by_user_id(db_session, user.id)
        if not remaining_subscriptions:
            await callback_query.message.edit_text(
                "Последняя подписка удалена.",
                reply_markup=get_back_to_profile_keyboard(),
            )
        else:
            await callback_query.message.edit_text(
                "Подписка удалена. Вот обновленный список:",
                reply_markup=get_profile_subscriptions_keyboard(
                    remaining_subscriptions
                ),
            )