import logging
import html
from typing import List
from datetime import datetime, timezone

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..constants import (
    INFO_TYPE_EVENTS,
    INFO_TYPE_NEWS,
    INFO_TYPE_WEATHER,
    KUDAGO_LOCATION_SLUGS,
)
from ..fsm import SubscriptionStates
from ..keyboards import get_frequency_keyboard, get_categories_keyboard

from app.database.crud import (
    create_subscription as db_create_subscription,
    delete_subscription as db_delete_subscription,
    get_subscription_by_user_and_type,
    get_subscriptions_by_user_id,
    get_user_by_telegram_id,
    log_user_action,
)
from app.database.models import Subscription
from app.database.session import get_session
from app.scheduler.main import scheduler
from app.scheduler.tasks import send_single_notification

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("subscribe"), StateFilter(None))
async def process_subscribe_command_start(message: types.Message, state: FSMContext):
    # ... (код без изменений) ...
    telegram_id = message.from_user.id
    with get_session() as db_session:
        user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if user and len(get_subscriptions_by_user_id(db_session, user.id)) >= 3:
            await message.answer(
                "У вас уже 3 активных подписки. Это максимальное количество.\n"
                "Вы можете удалить одну из существующих подписок с помощью /unsubscribe."
            )
            log_user_action(db_session, telegram_id, "/subscribe", "Limit reached")
            return
        log_user_action(db_session, telegram_id, "/subscribe", "Start process")
    keyboard_buttons = [
        [InlineKeyboardButton(text="🌦️ Погода", callback_data=f"subscribe_type:{INFO_TYPE_WEATHER}")],
        [InlineKeyboardButton(text="📰 Новости (США)", callback_data=f"subscribe_type:{INFO_TYPE_NEWS}")],
        [InlineKeyboardButton(text="🎉 События", callback_data=f"subscribe_type:{INFO_TYPE_EVENTS}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="subscribe_fsm_cancel")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer("На какой тип информации вы хотите подписаться?", reply_markup=keyboard)
    await state.set_state(SubscriptionStates.choosing_info_type)


@router.callback_query(StateFilter(SubscriptionStates.choosing_info_type), F.data.startswith("subscribe_type:"))
async def process_info_type_choice(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор типа информации (погода, новости, события).
    Для новостей и событий переводит на шаг выбора категории.
    Для погоды - на ввод города.
    """
    telegram_id = callback_query.from_user.id
    info_type = callback_query.data.split(":")[1]
    await state.update_data(info_type=info_type)

    with get_session() as db_session:
        log_user_action(db_session, telegram_id, "subscribe_step1", f"Type: {info_type}")

    if info_type in [INFO_TYPE_NEWS, INFO_TYPE_EVENTS]:
        await callback_query.message.edit_text(
            "Теперь выберите категорию:",
            reply_markup=get_categories_keyboard(info_type),
        )
        await state.set_state(SubscriptionStates.choosing_category)
    elif info_type == INFO_TYPE_WEATHER:
        await callback_query.message.edit_text("Вы выбрали 'Погода'.\nВведите город:")
        await state.set_state(SubscriptionStates.entering_city_weather)

    await callback_query.answer()


@router.callback_query(F.data == "subscribe_fsm_cancel")
async def callback_fsm_cancel_process(callback_query: types.CallbackQuery, state: FSMContext):
    # ... (код без изменений) ...
    telegram_id = callback_query.from_user.id
    with get_session() as db_session:
        log_user_action(db_session, telegram_id, "subscribe_fsm_cancel", "Cancelled by button")
    await callback_query.answer()
    await callback_query.message.edit_text("Процесс подписки отменен.")
    await state.clear()

@router.callback_query(StateFilter(SubscriptionStates.choosing_category), F.data.startswith("subscribe_category:"))
async def process_category_choice(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор категории для новостей или событий.
    Проверяет на дубликат подписки для новостей.
    """
    telegram_id = callback_query.from_user.id
    category_slug = callback_query.data.split(":")[1]
    user_data = await state.get_data()
    info_type = user_data.get("info_type")

    category_to_save = None if category_slug == "any" else category_slug

    # Проверка на дубликат подписки для новостей
    if info_type == INFO_TYPE_NEWS:
        with get_session() as db_session:
            user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
            if get_subscription_by_user_and_type(
                db_session, user.id, info_type, category=category_to_save
            ):
                category_name = category_to_save or "любая"
                await callback_query.message.edit_text(
                    f"Вы уже подписаны на 'Новости' (категория: {category_name})."
                )
                await state.clear()
                await callback_query.answer()
                return

    await state.update_data(category=category_to_save)

    if info_type == INFO_TYPE_NEWS:
        await callback_query.message.edit_text(
            "Категория выбрана. Теперь выберите частоту:",
            reply_markup=get_frequency_keyboard(),
        )
        await state.set_state(SubscriptionStates.choosing_frequency)
    elif info_type == INFO_TYPE_EVENTS:
        await callback_query.message.edit_text(
            "Категория выбрана. Теперь введите город (например, Москва или спб):"
        )
        await state.set_state(SubscriptionStates.entering_city_events)

    await callback_query.answer()


@router.message(StateFilter(SubscriptionStates.entering_city_weather), F.text)
async def process_city_for_weather_subscription(message: types.Message, state: FSMContext):
    # ... (код без изменений) ...
    city_name = message.text.strip()
    if not city_name:
        await message.reply("Название города не может быть пустым.")
        return
    with get_session() as db_session:
        user = get_user_by_telegram_id(session=db_session, telegram_id=message.from_user.id)
        if get_subscription_by_user_and_type(db_session, user.id, INFO_TYPE_WEATHER, city_name):
            await message.answer(f"Вы уже подписаны на погоду в городе '{html.escape(city_name)}'.")
            await state.clear()
            return
    await state.update_data(details=city_name)
    await message.answer(f"Город '{html.escape(city_name)}' принят.\nВыберите частоту:",
                         reply_markup=get_frequency_keyboard())
    await state.set_state(SubscriptionStates.choosing_frequency)


@router.message(StateFilter(SubscriptionStates.entering_city_events), F.text)
async def process_city_for_events_subscription(message: types.Message, state: FSMContext):
    city_name = message.text.strip()
    location_slug = KUDAGO_LOCATION_SLUGS.get(city_name.lower())
    if not location_slug:
        await message.reply(f"Город '{html.escape(city_name)}' не поддерживается.")
        return

    user_data = await state.get_data()
    category = user_data.get("category")

    with get_session() as db_session:
        user = get_user_by_telegram_id(session=db_session, telegram_id=message.from_user.id)
        if get_subscription_by_user_and_type(
            db_session, user.id, INFO_TYPE_EVENTS, location_slug, category
        ):
            await message.answer(
                f"У вас уже есть такая подписка (События: {html.escape(city_name)}, Категория: {category or 'любая'})."
            )
            await state.clear()
            return

    await state.update_data(details=location_slug)
    await message.answer(
        f"Город '{html.escape(city_name)}' принят.\nВыберите частоту:",
        reply_markup=get_frequency_keyboard(),
    )
    await state.set_state(SubscriptionStates.choosing_frequency)


# --- ИЗМЕНЕНО: Обработчик выбора частоты ---
@router.callback_query(
    StateFilter(SubscriptionStates.choosing_frequency),
    F.data.startswith("frequency:") | F.data.startswith("cron:"),
)
async def process_frequency_choice(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор частоты (интервал или cron), завершает подписку
    и добавляет задачу в планировщик.
    """
    await callback_query.answer()
    telegram_id = callback_query.from_user.id
    user_data = await state.get_data()

    # Параметры для создания подписки и задачи
    sub_params = {}
    job_params = {}
    callback_data = callback_query.data

    if callback_data.startswith("frequency:"):
        frequency_hours = int(callback_data.split(":")[1])
        sub_params["frequency"] = frequency_hours
        job_params = {"trigger": "interval", "hours": frequency_hours}
        log_details = f"Data: {user_data}, Freq: {frequency_hours}h"
    elif callback_data.startswith("cron:"):
        time_str = callback_data.split(":", 1)[1]
        hour, minute = map(int, time_str.split(":"))
        cron_expr = f"{minute} {hour} * * *"  # APScheduler cron format
        sub_params["cron_expression"] = cron_expr
        job_params = {"trigger": "cron", "hour": hour, "minute": minute}
        log_details = f"Data: {user_data}, Cron: {time_str}"
    else:
        await callback_query.message.edit_text("Произошла ошибка. Попробуйте снова.")
        return

    new_subscription = None
    with get_session() as db_session:
        user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        new_subscription = db_create_subscription(
            session=db_session,
            user_id=user.id,
            info_type=user_data["info_type"],
            details=user_data.get("details"),
            category=user_data.get("category"),
            **sub_params,
        )
        log_user_action(db_session, telegram_id, "subscribe_finish", log_details)

    if new_subscription:
        job_id = f"sub_{new_subscription.id}"
        try:
            # Запускаем первую отправку немедленно для лучшего UX
            # await send_single_notification(bot=callback_query.bot, subscription_id=new_subscription.id)

            scheduler.add_job(
                send_single_notification,
                id=job_id,
                kwargs={"subscription_id": new_subscription.id},
                replace_existing=True,
                # Убираем next_run_time, чтобы он сработал согласно триггеру
                **job_params,
            )
            logger.info(f"Задача {job_id} динамически добавлена в планировщик. Params: {job_params}")
            await callback_query.message.edit_text("Вы успешно подписались!")
        except Exception as e:
            logger.error(f"Ошибка при добавлении задачи {job_id} в планировщик: {e}", exc_info=True)
            await callback_query.message.edit_text(
                "Подписка создана, но произошла ошибка с ее активацией. Обратитесь к администратору."
            )
    else:
        await callback_query.message.edit_text("Произошла ошибка при создании подписки.")

    await state.clear()


# --- ИЗМЕНЕНО: Отображение подписок ---
@router.message(Command("mysubscriptions"))
async def process_mysubscriptions_command(message: types.Message):
    telegram_id = message.from_user.id
    with get_session() as db_session:
        user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if not user:
            await message.answer("Не удалось найти информацию о вас.")
            return
        subscriptions: List[Subscription] = get_subscriptions_by_user_id(db_session, user.id)
        if not subscriptions:
            await message.answer("У вас пока нет активных подписок.")
            return
        response_lines = ["<b>📋 Ваши активные подписки:</b>"]
        for i, sub in enumerate(subscriptions):
            schedule_str = ""
            if sub.frequency:
                schedule_str = f"раз в {sub.frequency} ч."
            elif sub.cron_expression:
                # Простое преобразование для отображения
                parts = sub.cron_expression.split()
                schedule_str = f"ежедневно в {int(parts[1]):02d}:{int(parts[0]):02d} (UTC)"

            details_str = ""
            if sub.info_type == INFO_TYPE_WEATHER:
                details_str = f"Погода: <b>{html.escape(sub.details)}</b>"
            elif sub.info_type == INFO_TYPE_NEWS:
                category_str = f" ({sub.category or 'все'})"
                details_str = f"Новости (США){category_str}"
            elif sub.info_type == INFO_TYPE_EVENTS:
                city_name = next(
                    (name.capitalize() for name, slug in KUDAGO_LOCATION_SLUGS.items() if slug == sub.details),
                    sub.details)
                category_str = f" ({sub.category or 'все'})"
                details_str = f"События: <b>{html.escape(city_name)}</b>{category_str}"

            response_lines.append(f"{i + 1}. {details_str} ({schedule_str})")
            await message.answer("\n".join(response_lines))


@router.message(Command("unsubscribe"))
async def process_unsubscribe_command_start(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    with get_session() as db_session:
        user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if not user:
            await message.answer("Не удалось найти информацию о вас.")
            return
        subscriptions = get_subscriptions_by_user_id(db_session, user.id)
        if not subscriptions:
            await message.answer("У вас нет активных подписок для отмены.")
            return
        keyboard_buttons = []
        for sub in subscriptions:
            schedule_str = ""
            if sub.frequency:
                schedule_str = f"раз в {sub.frequency} ч."
            elif sub.cron_expression:
                parts = sub.cron_expression.split()
                schedule_str = f"ежедневно в {int(parts[1]):02d}:{int(parts[0]):02d} (UTC)"

            details_str = ""
            if sub.info_type == INFO_TYPE_WEATHER:
                details_str = f"Погода: {html.escape(sub.details)}"
            elif sub.info_type == INFO_TYPE_NEWS:
                category_str = f" ({sub.category or 'все'})"
                details_str = f"Новости (США){category_str}"
            elif sub.info_type == INFO_TYPE_EVENTS:
                city_name = next(
                    (name.capitalize() for name, slug in KUDAGO_LOCATION_SLUGS.items() if slug == sub.details),
                    sub.details)
                category_str = f" ({sub.category or 'все'})"
                details_str = f"События: {html.escape(city_name)}{category_str}"
            keyboard_buttons.append([InlineKeyboardButton(text=f"❌ {details_str} ({schedule_str})",
                                                          callback_data=f"unsubscribe_confirm:{sub.id}")])
        keyboard_buttons.append(
            [InlineKeyboardButton(text="Отменить операцию", callback_data="unsubscribe_action_cancel")])
        await message.answer("Выберите подписку для отписки:",
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))
        log_user_action(db_session, telegram_id, "/unsubscribe", "Start process")


@router.callback_query(F.data.startswith("unsubscribe_confirm:"))
async def process_unsubscribe_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    # ... (код без изменений) ...
    await callback_query.answer()
    sub_id = int(callback_query.data.split(":")[1])
    telegram_id = callback_query.from_user.id
    job_id = f"sub_{sub_id}"

    with get_session() as db_session:
        user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        sub_to_delete = db_session.get(Subscription, sub_id)

        if not user or not sub_to_delete or sub_to_delete.user_id != user.id:
            await callback_query.message.edit_text("Ошибка: подписка не найдена.")
            return

        db_delete_subscription(db_session, sub_id)

        try:
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
                logger.info(f"Задача {job_id} успешно удалена из планировщика.")
            else:
                logger.warning(f"Задача {job_id} для удаления не найдена в планировщике.")
        except Exception as e:
            logger.error(f"Ошибка при удалении задачи {job_id} из планировщика: {e}", exc_info=True)

        await callback_query.message.edit_text("Вы успешно отписались.")
        log_user_action(db_session, telegram_id, "unsubscribe_confirm", f"Sub ID: {sub_id}")


@router.callback_query(F.data == "unsubscribe_action_cancel")
async def process_unsubscribe_action_cancel(callback_query: types.CallbackQuery, state: FSMContext):
    # ... (код без изменений) ...
    await callback_query.answer()
    await callback_query.message.edit_text("Операция отписки отменена.")
    with get_session() as db_session:
        log_user_action(db_session, callback_query.from_user.id, "unsubscribe_cancel")