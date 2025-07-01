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
from ..keyboards import (
    get_frequency_keyboard,
    get_categories_keyboard,
    get_city_selection_keyboard,
)
from ..data.cities import RUSSIAN_CITIES

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
        await callback_query.message.edit_text(
            "Вы выбрали 'Погода'.\n"
            "Начните вводить название города (минимум 3 буквы), и я предложу варианты."
        )
        await state.set_state(SubscriptionStates.prompting_city_search)

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
            "Категория выбрана. Теперь начните вводить название города (минимум 3 буквы):"
        )
        await state.set_state(SubscriptionStates.prompting_city_search)

    await callback_query.answer()


@router.message(StateFilter(SubscriptionStates.prompting_city_search), F.text)
async def process_city_search(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод пользователя для поиска города.
    """
    if not message.text:
        return
    query = message.text.strip()
    if len(query) < 3:
        await message.answer("Пожалуйста, введите минимум 3 буквы для поиска.")
        return

    # Ищем города, содержащие запрос пользователя (без учета регистра)
    found_cities = [
        city for city in RUSSIAN_CITIES if query.lower() in city.lower()
    ]

    if not found_cities:
        await message.answer(
            "К сожалению, по вашему запросу ничего не найдено. Попробуйте еще раз."
        )
        return

    # Ограничиваем количество кнопок для удобства
    keyboard = get_city_selection_keyboard(found_cities[:10])
    await message.answer(
        "Вот что удалось найти. Пожалуйста, выберите ваш город:", reply_markup=keyboard
    )
    await state.set_state(SubscriptionStates.choosing_city_from_list)


@router.callback_query(
    StateFilter(SubscriptionStates.choosing_city_from_list),
    F.data.startswith("city_select:"),
)
async def process_city_selection(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор города из предложенного списка.
    """
    await callback_query.answer()
    selected_city = callback_query.data.split(":", 1)[1]

    user_data = await state.get_data()
    info_type = user_data.get("info_type")
    category = user_data.get("category")
    details_to_save = selected_city  # По умолчанию для погоды

    # Для событий нужно получить slug
    if info_type == INFO_TYPE_EVENTS:
        location_slug = KUDAGO_LOCATION_SLUGS.get(selected_city.lower())
        if not location_slug:
            await callback_query.message.edit_text(
                f"К сожалению, город '{html.escape(selected_city)}' больше не поддерживается для событий. "
                "Пожалуйста, начните подписку заново с помощью /subscribe."
            )
            await state.clear()
            return
        details_to_save = location_slug

    # Проверка на дубликат подписки
    with get_session() as db_session:
        user = get_user_by_telegram_id(
            session=db_session, telegram_id=callback_query.from_user.id
        )
        if get_subscription_by_user_and_type(
            db_session, user.id, info_type, details_to_save, category
        ):
            await callback_query.message.edit_text(
                f"У вас уже есть такая подписка."
            )
            await state.clear()
            return

    await state.update_data(details=details_to_save)
    await callback_query.message.edit_text(
        f"Город '{html.escape(selected_city)}' выбран.\nТеперь выберите частоту:",
        reply_markup=get_frequency_keyboard(),
    )
    await state.set_state(SubscriptionStates.choosing_frequency)


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
        cron_expr = f"{minute} {hour} * * *"
        sub_params["cron_expression"] = cron_expr
        job_params = {"trigger": "cron", "hour": hour, "minute": minute}
        log_details = f"Data: {user_data}, Cron: {time_str}"
    else:
        await callback_query.message.edit_text("Произошла ошибка. Попробуйте снова.")
        return

    with get_session() as db_session:
        user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if not user:
            await callback_query.message.edit_text("Ошибка: ваш профиль не найден.")
            await state.clear()
            return

        new_subscription = db_create_subscription(
            session=db_session,
            user_id=user.id,
            info_type=user_data["info_type"],
            details=user_data.get("details"),
            category=user_data.get("category"),
            **sub_params,
        )
        log_user_action(db_session, telegram_id, "subscribe_finish", log_details)

        if new_subscription and new_subscription.id:
            job_id = f"sub_{new_subscription.id}"
            job_kwargs = {
                "bot": callback_query.bot,
                "subscription_id": new_subscription.id,
            }
            try:
                scheduler.add_job(
                    send_single_notification,
                    id=job_id,
                    kwargs=job_kwargs,
                    replace_existing=True,
                    **job_params,
                )
                logger.info(
                    f"Задача {job_id} динамически добавлена. Params: {job_params}"
                )
                await callback_query.message.edit_text("Вы успешно подписались!")
            except Exception as e:
                logger.error(
                    f"Ошибка при добавлении задачи {job_id} в планировщик: {e}",
                    exc_info=True,
                )
                await callback_query.message.edit_text(
                    "Подписка создана, но произошла ошибка с ее активацией. Обратитесь к администратору."
                )
        else:
            await callback_query.message.edit_text(
                "Произошла ошибка при создании подписки."
            )

    await state.clear()


@router.message(Command("mysubscriptions"))
async def process_mysubscriptions_command(message: types.Message):
    await message.answer(
        "💡 Для более удобного управления подписками воспользуйтесь командой /profile."
    )
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
    await callback_query.answer()
    await callback_query.message.edit_text("Операция отписки отменена.")
    with get_session() as db_session:
        log_user_action(db_session, callback_query.from_user.id, "unsubscribe_cancel")