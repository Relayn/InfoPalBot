# Файл tests/integration/test_subscription_flow.py

import pytest
import html
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from typing import Optional

from sqlmodel import Session, select

from app.bot.main import (
    process_subscribe_command_start,
    process_info_type_choice,
    SubscriptionStates,
)
from app.config import settings as app_settings
from app.database.models import Log, User as DBUser, Subscription
from app.database.crud import create_user, get_subscription_by_user_and_type
from app.bot.constants import INFO_TYPE_NEWS, INFO_TYPE_WEATHER, INFO_TYPE_EVENTS, KUDAGO_LOCATION_SLUGS
from aiogram.types import Message, User as AiogramUser, Chat, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from app.bot.main import process_city_for_weather_subscription
from app.bot.main import process_city_for_events_subscription

# Вспомогательная функция для создания mock FSMContext
async def get_mock_fsm_context(initial_state: Optional[SubscriptionStates] = None,
                               initial_data: Optional[dict] = None) -> FSMContext:
    """Создает и возвращает мок FSMContext с MemoryStorage."""
    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=MagicMock(chat_id=123, user_id=123, bot_id=42))
    if initial_state:
        await state.set_state(initial_state)
    if initial_data:
        await state.set_data(initial_data)
    return state


@pytest.mark.asyncio
async def test_subscribe_to_news_successful_flow(integration_session: Session):
    """
    Интеграционный тест: успешная подписка на новости.
    Проверяет: /subscribe -> выбор типа "Новости" -> создание подписки в БД -> очистка FSM.
    """
    telegram_user_id = 777001

    # --- Шаг 1: Пользователь отправляет команду /subscribe ---
    mock_message_subscribe = AsyncMock(spec=Message)
    mock_message_subscribe.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id, full_name="Subscriber User")
    mock_message_subscribe.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message_subscribe.answer = AsyncMock()

    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    mock_fsm_context_subscribe = await get_mock_fsm_context()
    mock_fsm_context_subscribe.set_state = AsyncMock()  # Мокируем для проверки вызова
    mock_fsm_context_subscribe.get_state = AsyncMock(return_value=None)

    mock_session_cm_subscribe = MagicMock()
    mock_session_cm_subscribe.__enter__.return_value = integration_session
    mock_session_cm_subscribe.__exit__ = MagicMock(return_value=None)
    mock_generator_subscribe = MagicMock()
    mock_generator_subscribe.__next__.return_value = mock_session_cm_subscribe

    with patch('app.bot.main.get_session', return_value=mock_generator_subscribe):
        await process_subscribe_command_start(mock_message_subscribe, mock_fsm_context_subscribe)

    # Проверки для Шага 1
    mock_message_subscribe.answer.assert_called_once()
    args_subscribe, kwargs_subscribe = mock_message_subscribe.answer.call_args
    assert "На какой тип информации вы хотите подписаться?" in args_subscribe[0]
    assert isinstance(kwargs_subscribe['reply_markup'], InlineKeyboardMarkup)

    news_button_found = False
    for row in kwargs_subscribe['reply_markup'].inline_keyboard:
        for button in row:
            if button.text == "📰 Новости (Россия)" and button.callback_data == f"subscribe_type:{INFO_TYPE_NEWS}":
                news_button_found = True
                break
        if news_button_found:
            break
    assert news_button_found, "Кнопка подписки на новости не найдена"

    mock_fsm_context_subscribe.set_state.assert_called_once_with(SubscriptionStates.choosing_info_type)

    log_entry_step1 = integration_session.exec(
        select(Log).where(Log.command == "/subscribe").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry_step1 is not None
    assert log_entry_step1.details == "Start subscription process"

    # --- Шаг 2: Пользователь выбирает "Новости" ---
    mock_callback_query_news = AsyncMock(spec=CallbackQuery)
    mock_callback_query_news.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id)
    mock_callback_query_news.data = f"subscribe_type:{INFO_TYPE_NEWS}"
    mock_callback_query_news.message = AsyncMock(spec=Message)
    mock_callback_query_news.message.edit_text = AsyncMock()
    mock_callback_query_news.answer = AsyncMock()

    # Для второго шага FSMContext должен быть в состоянии choosing_info_type
    # Мы передаем это состояние в наш мок-генератор FSMContext
    # И также мокируем методы, которые будут вызваны в process_info_type_choice
    mock_fsm_context_callback = await get_mock_fsm_context(
        initial_state=SubscriptionStates.choosing_info_type
    )
    mock_fsm_context_callback.update_data = AsyncMock()
    mock_fsm_context_callback.clear = AsyncMock()

    mock_session_cm_callback = MagicMock()
    mock_session_cm_callback.__enter__.return_value = integration_session
    mock_session_cm_callback.__exit__ = MagicMock(return_value=None)
    mock_generator_callback = MagicMock()
    mock_generator_callback.__next__.return_value = mock_session_cm_callback

    with patch('app.bot.main.get_session', return_value=mock_generator_callback):
        await process_info_type_choice(mock_callback_query_news, mock_fsm_context_callback)

    # Проверки для Шага 2
    mock_callback_query_news.answer.assert_called_once()
    mock_fsm_context_callback.update_data.assert_called_once_with(info_type=INFO_TYPE_NEWS)

    mock_callback_query_news.message.edit_text.assert_called_once()
    args_edit, _ = mock_callback_query_news.message.edit_text.call_args
    assert "Вы успешно подписались на 'Новости (Россия)'" in args_edit[0]
    assert "daily" in args_edit[0]

    subscription_in_db = get_subscription_by_user_and_type(
        session=integration_session, user_id=db_user.id, info_type=INFO_TYPE_NEWS
    )
    assert subscription_in_db is not None
    assert subscription_in_db.status == "active"
    assert subscription_in_db.frequency == "daily"
    assert subscription_in_db.details is None

    mock_fsm_context_callback.clear.assert_called_once()

    log_entries_step2 = integration_session.exec(
        select(Log).where(Log.user_id == db_user.id).order_by(Log.timestamp.desc()).limit(2)
    ).all()

    assert len(log_entries_step2) >= 2

    log_confirm_found = any(
        entry.command == "subscribe_confirm" and
        entry.details == f"Type: {INFO_TYPE_NEWS}, Freq: daily"
        for entry in log_entries_step2
    )
    log_type_selected_found = any(
        entry.command == "subscribe_type_selected" and
        entry.details == f"Type chosen: {INFO_TYPE_NEWS}"
        for entry in log_entries_step2
    )
    assert log_confirm_found, "Лог 'subscribe_confirm' не найден или некорректен"
    assert log_type_selected_found, "Лог 'subscribe_type_selected' не найден или некорректен"


# Файл tests/integration/test_subscription_flow.py
# ... (импорты, get_mock_fsm_context и тест test_subscribe_to_news_successful_flow как есть) ...

@pytest.mark.asyncio
async def test_subscribe_to_news_already_subscribed_flow(integration_session: Session):
    """
    Интеграционный тест: попытка подписки на новости, когда пользователь уже подписан.
    Проверяет: /subscribe -> выбор "Новости" -> сообщение "уже подписан" -> нет новой подписки в БД.
    """
    telegram_user_id = 777002
    default_frequency = "daily"  # Частота по умолчанию, используемая в main.py

    # --- Шаг 0: Создаем пользователя и существующую подписку на новости ---
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)
    # Создаем существующую подписку
    existing_sub = Subscription(
        user_id=db_user.id,
        info_type=INFO_TYPE_NEWS,
        frequency=default_frequency,
        details=None,  # Для новостей детали не важны
        status="active"
    )
    integration_session.add(existing_sub)
    integration_session.commit()
    integration_session.refresh(existing_sub)

    # --- Шаг 1: Пользователь отправляет команду /subscribe ---
    mock_message_subscribe = AsyncMock(spec=Message)
    mock_message_subscribe.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id, full_name="AlreadySub User")
    mock_message_subscribe.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message_subscribe.answer = AsyncMock()

    mock_fsm_context_subscribe = await get_mock_fsm_context()
    mock_fsm_context_subscribe.set_state = AsyncMock()
    mock_fsm_context_subscribe.get_state = AsyncMock(return_value=None)

    mock_session_cm_subscribe = MagicMock()
    mock_session_cm_subscribe.__enter__.return_value = integration_session
    mock_session_cm_subscribe.__exit__ = MagicMock(return_value=None)
    mock_generator_subscribe = MagicMock()
    mock_generator_subscribe.__next__.return_value = mock_session_cm_subscribe

    with patch('app.bot.main.get_session', return_value=mock_generator_subscribe):
        await process_subscribe_command_start(mock_message_subscribe, mock_fsm_context_subscribe)

    # Проверки для Шага 1 (минимальные, так как этот шаг уже покрыт другим тестом)
    mock_message_subscribe.answer.assert_called_once()
    mock_fsm_context_subscribe.set_state.assert_called_once_with(SubscriptionStates.choosing_info_type)

    # --- Шаг 2: Пользователь выбирает "Новости" ---
    mock_callback_query_news = AsyncMock(spec=CallbackQuery)
    mock_callback_query_news.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id)
    mock_callback_query_news.data = f"subscribe_type:{INFO_TYPE_NEWS}"
    mock_callback_query_news.message = AsyncMock(spec=Message)
    mock_callback_query_news.message.edit_text = AsyncMock()
    mock_callback_query_news.answer = AsyncMock()

    mock_fsm_context_callback = await get_mock_fsm_context(
        initial_state=SubscriptionStates.choosing_info_type
    )
    mock_fsm_context_callback.update_data = AsyncMock()  # Будет вызван
    mock_fsm_context_callback.clear = AsyncMock()  # Будет вызван

    mock_session_cm_callback = MagicMock()
    mock_session_cm_callback.__enter__.return_value = integration_session
    mock_session_cm_callback.__exit__ = MagicMock(return_value=None)
    mock_generator_callback = MagicMock()
    mock_generator_callback.__next__.return_value = mock_session_cm_callback

    with patch('app.bot.main.get_session', return_value=mock_generator_callback):
        await process_info_type_choice(mock_callback_query_news, mock_fsm_context_callback)

    # Проверки для Шага 2
    mock_callback_query_news.answer.assert_called_once()
    mock_fsm_context_callback.update_data.assert_called_once_with(info_type=INFO_TYPE_NEWS)

    mock_callback_query_news.message.edit_text.assert_called_once()
    args_edit, _ = mock_callback_query_news.message.edit_text.call_args
    assert "Вы уже подписаны на 'Новости (Россия)'." in args_edit[0]

    # Проверка, что НОВАЯ подписка НЕ создана (должна остаться только одна)
    all_news_subscriptions = integration_session.exec(
        select(Subscription).where(
            Subscription.user_id == db_user.id,
            Subscription.info_type == INFO_TYPE_NEWS,
            Subscription.status == "active"
        )
    ).all()
    assert len(all_news_subscriptions) == 1, "Должна быть только одна активная подписка на новости"
    assert all_news_subscriptions[0].id == existing_sub.id  # Убедимся, что это та же самая подписка

    mock_fsm_context_callback.clear.assert_called_once()

    # Проверка логов для шага 2
    log_entries_step2 = integration_session.exec(
        select(Log).where(Log.user_id == db_user.id).order_by(Log.timestamp.desc()).limit(2)
    ).all()

    # Ожидаем лог о попытке дублирующей подписки и лог о выборе типа
    log_duplicate_found = any(
        entry.command == "subscribe_attempt_duplicate" and
        entry.details == f"Type: {INFO_TYPE_NEWS}"
        for entry in log_entries_step2
    )
    log_type_selected_found = any(
        entry.command == "subscribe_type_selected" and
        entry.details == f"Type chosen: {INFO_TYPE_NEWS}"
        for entry in log_entries_step2
    )
    assert log_duplicate_found, "Лог 'subscribe_attempt_duplicate' не найден или некорректен"
    assert log_type_selected_found, "Лог 'subscribe_type_selected' не найден или некорректен"


@pytest.mark.asyncio
async def test_subscribe_to_weather_successful_flow(integration_session: Session):
    """
    Интеграционный тест: успешная подписка на погоду.
    Проверяет: /subscribe -> выбор "Погода" -> ввод города -> создание подписки в БД -> очистка FSM.
    """
    telegram_user_id = 777003
    city_to_subscribe = "Лондон"
    default_frequency = "daily"

    # --- Шаг 0: Создаем пользователя ---
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    # --- Шаг 1: Пользователь отправляет команду /subscribe ---
    mock_message_subscribe = AsyncMock(spec=Message)
    mock_message_subscribe.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id, full_name="Weather Sub User")
    mock_message_subscribe.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message_subscribe.answer = AsyncMock()

    mock_fsm_context_step1 = await get_mock_fsm_context()
    mock_fsm_context_step1.set_state = AsyncMock()  # Мокируем для проверки вызова
    # get_state не мокируем здесь, т.к. process_subscribe_command_start не читает состояние

    mock_session_cm_step1 = MagicMock()
    mock_session_cm_step1.__enter__.return_value = integration_session
    mock_session_cm_step1.__exit__ = MagicMock(return_value=None)
    mock_generator_step1 = MagicMock()
    mock_generator_step1.__next__.return_value = mock_session_cm_step1

    with patch('app.bot.main.get_session', return_value=mock_generator_step1):
        await process_subscribe_command_start(mock_message_subscribe, mock_fsm_context_step1)

    # Проверки для Шага 1
    mock_message_subscribe.answer.assert_called_once()  # Проверяем, что ответ был
    mock_fsm_context_step1.set_state.assert_called_once_with(SubscriptionStates.choosing_info_type)
    # Лог для шага 1
    log_step1 = integration_session.exec(
        select(Log).where(Log.user_id == db_user.id, Log.command == "/subscribe")
    ).first()
    assert log_step1 and log_step1.details == "Start subscription process"

    # --- Шаг 2: Пользователь выбирает "Погода" ---
    mock_callback_query_weather = AsyncMock(spec=CallbackQuery)
    mock_callback_query_weather.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id)
    mock_callback_query_weather.data = f"subscribe_type:{INFO_TYPE_WEATHER}"
    mock_callback_query_weather.message = AsyncMock(spec=Message)
    mock_callback_query_weather.message.edit_text = AsyncMock()
    mock_callback_query_weather.answer = AsyncMock()

    # FSMContext для этого шага должен быть в состоянии choosing_info_type
    mock_fsm_context_step2 = await get_mock_fsm_context(initial_state=SubscriptionStates.choosing_info_type)
    mock_fsm_context_step2.update_data = AsyncMock()
    mock_fsm_context_step2.set_state = AsyncMock()  # Мокируем для проверки вызова нового состояния

    mock_session_cm_step2 = MagicMock()
    mock_session_cm_step2.__enter__.return_value = integration_session
    mock_session_cm_step2.__exit__ = MagicMock(return_value=None)
    mock_generator_step2 = MagicMock()
    mock_generator_step2.__next__.return_value = mock_session_cm_step2

    with patch('app.bot.main.get_session', return_value=mock_generator_step2):
        await process_info_type_choice(mock_callback_query_weather, mock_fsm_context_step2)

    # Проверки для Шага 2
    mock_callback_query_weather.answer.assert_called_once()
    mock_fsm_context_step2.update_data.assert_called_once_with(info_type=INFO_TYPE_WEATHER)
    mock_callback_query_weather.message.edit_text.assert_called_once_with(
        "Вы выбрали 'Погода'.\nПожалуйста, введите название города..."
    )
    mock_fsm_context_step2.set_state.assert_called_once_with(SubscriptionStates.entering_city_weather)
    # Лог для шага 2
    log_step2 = integration_session.exec(
        select(Log).where(Log.user_id == db_user.id, Log.command == "subscribe_type_selected")
    ).first()
    assert log_step2 and log_step2.details == f"Type chosen: {INFO_TYPE_WEATHER}"

    # --- Шаг 3: Пользователь вводит название города ---
    mock_message_city_input = AsyncMock(spec=Message)
    mock_message_city_input.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id)
    mock_message_city_input.chat = MagicMock(spec=Chat, id=telegram_user_id)  # Нужен для reply/answer
    mock_message_city_input.text = city_to_subscribe
    mock_message_city_input.answer = AsyncMock()  # Для ответа об успехе

    # FSMContext для этого шага должен быть в состоянии entering_city_weather
    # и содержать info_type из предыдущего шага
    mock_fsm_context_step3 = await get_mock_fsm_context(
        initial_state=SubscriptionStates.entering_city_weather,
        initial_data={'info_type': INFO_TYPE_WEATHER}
    )
    mock_fsm_context_step3.clear = AsyncMock()  # Мокируем для проверки очистки состояния

    mock_session_cm_step3 = MagicMock()
    mock_session_cm_step3.__enter__.return_value = integration_session
    mock_session_cm_step3.__exit__ = MagicMock(return_value=None)
    mock_generator_step3 = MagicMock()
    mock_generator_step3.__next__.return_value = mock_session_cm_step3

    with patch('app.bot.main.get_session', return_value=mock_generator_step3):
        await process_city_for_weather_subscription(mock_message_city_input, mock_fsm_context_step3)

    # Проверки для Шага 3
    mock_message_city_input.answer.assert_called_once_with(
        f"Вы успешно подписались на '{INFO_TYPE_WEATHER}' для города '{html.escape(city_to_subscribe)}' с частотой '{default_frequency}'."
    )

    # Проверка создания подписки в БД
    subscription_in_db = get_subscription_by_user_and_type(
        session=integration_session,
        user_id=db_user.id,
        info_type=INFO_TYPE_WEATHER,
        details=city_to_subscribe
    )
    assert subscription_in_db is not None
    assert subscription_in_db.status == "active"
    assert subscription_in_db.frequency == default_frequency
    assert subscription_in_db.details == city_to_subscribe

    mock_fsm_context_step3.clear.assert_called_once()

    # Лог для шага 3
    log_step3 = integration_session.exec(
        select(Log).where(Log.user_id == db_user.id, Log.command == "subscribe_confirm")
    ).first()
    assert log_step3 is not None
    assert log_step3.details == f"Type: {INFO_TYPE_WEATHER}, City: {city_to_subscribe}, Freq: {default_frequency}"


@pytest.mark.asyncio
async def test_subscribe_to_events_successful_flow(integration_session: Session):
    """
    Интеграционный тест: успешная подписка на события.
    Проверяет: /subscribe -> выбор "События" -> ввод города -> создание подписки в БД -> очистка FSM.
    """
    telegram_user_id = 777004
    city_input_by_user = "Москва"  # Как пользователь вводит
    expected_location_slug = KUDAGO_LOCATION_SLUGS[city_input_by_user.lower()]
    default_frequency = "daily"

    # --- Шаг 0: Создаем пользователя ---
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    # --- Шаг 1: Пользователь отправляет команду /subscribe ---
    mock_message_subscribe = AsyncMock(spec=Message)
    mock_message_subscribe.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id, full_name="Events Sub User")
    mock_message_subscribe.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message_subscribe.answer = AsyncMock()

    mock_fsm_context_step1 = await get_mock_fsm_context()
    mock_fsm_context_step1.set_state = AsyncMock()

    mock_session_cm_step1 = MagicMock()
    mock_session_cm_step1.__enter__.return_value = integration_session
    mock_session_cm_step1.__exit__ = MagicMock(return_value=None)
    mock_generator_step1 = MagicMock()
    mock_generator_step1.__next__.return_value = mock_session_cm_step1

    with patch('app.bot.main.get_session', return_value=mock_generator_step1):
        await process_subscribe_command_start(mock_message_subscribe, mock_fsm_context_step1)

    # Проверки для Шага 1
    mock_message_subscribe.answer.assert_called_once()
    mock_fsm_context_step1.set_state.assert_called_once_with(SubscriptionStates.choosing_info_type)
    log_step1 = integration_session.exec(
        select(Log).where(Log.user_id == db_user.id, Log.command == "/subscribe")
    ).first()
    assert log_step1 and log_step1.details == "Start subscription process"

    # --- Шаг 2: Пользователь выбирает "События" ---
    mock_callback_query_events = AsyncMock(spec=CallbackQuery)
    mock_callback_query_events.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id)
    mock_callback_query_events.data = f"subscribe_type:{INFO_TYPE_EVENTS}"
    mock_callback_query_events.message = AsyncMock(spec=Message)
    mock_callback_query_events.message.edit_text = AsyncMock()
    mock_callback_query_events.answer = AsyncMock()

    mock_fsm_context_step2 = await get_mock_fsm_context(initial_state=SubscriptionStates.choosing_info_type)
    mock_fsm_context_step2.update_data = AsyncMock()
    mock_fsm_context_step2.set_state = AsyncMock()

    mock_session_cm_step2 = MagicMock()
    mock_session_cm_step2.__enter__.return_value = integration_session
    mock_session_cm_step2.__exit__ = MagicMock(return_value=None)
    mock_generator_step2 = MagicMock()
    mock_generator_step2.__next__.return_value = mock_session_cm_step2

    with patch('app.bot.main.get_session', return_value=mock_generator_step2):
        await process_info_type_choice(mock_callback_query_events, mock_fsm_context_step2)

    # Проверки для Шага 2
    mock_callback_query_events.answer.assert_called_once()
    mock_fsm_context_step2.update_data.assert_called_once_with(info_type=INFO_TYPE_EVENTS)
    mock_callback_query_events.message.edit_text.assert_called_once_with(
        "Вы выбрали 'События'.\nПожалуйста, введите название города (например, Москва, спб)."
    )
    mock_fsm_context_step2.set_state.assert_called_once_with(SubscriptionStates.entering_city_events)
    log_step2 = integration_session.exec(
        select(Log).where(Log.user_id == db_user.id, Log.command == "subscribe_type_selected")
    ).first()  # Предполагаем, что это последний лог такого типа
    assert log_step2 and log_step2.details == f"Type chosen: {INFO_TYPE_EVENTS}"

    # --- Шаг 3: Пользователь вводит название города ---
    mock_message_city_input = AsyncMock(spec=Message)
    mock_message_city_input.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id)
    mock_message_city_input.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message_city_input.text = city_input_by_user
    mock_message_city_input.answer = AsyncMock()
    mock_message_city_input.reply = AsyncMock()  # process_city_for_events_subscription может использовать reply

    mock_fsm_context_step3 = await get_mock_fsm_context(
        initial_state=SubscriptionStates.entering_city_events,
        initial_data={'info_type': INFO_TYPE_EVENTS}
    )
    mock_fsm_context_step3.clear = AsyncMock()

    mock_session_cm_step3 = MagicMock()
    mock_session_cm_step3.__enter__.return_value = integration_session
    mock_session_cm_step3.__exit__ = MagicMock(return_value=None)
    mock_generator_step3 = MagicMock()
    mock_generator_step3.__next__.return_value = mock_session_cm_step3

    with patch('app.bot.main.get_session', return_value=mock_generator_step3):
        await process_city_for_events_subscription(mock_message_city_input, mock_fsm_context_step3)

    # Проверки для Шага 3
    mock_message_city_input.answer.assert_called_once_with(
        f"Вы успешно подписались на '{INFO_TYPE_EVENTS}' для города '{html.escape(city_input_by_user)}' с частотой '{default_frequency}'."
    )

    subscription_in_db = get_subscription_by_user_and_type(
        session=integration_session,
        user_id=db_user.id,
        info_type=INFO_TYPE_EVENTS,
        details=expected_location_slug  # В БД хранится slug
    )
    assert subscription_in_db is not None
    assert subscription_in_db.status == "active"
    assert subscription_in_db.frequency == default_frequency
    assert subscription_in_db.details == expected_location_slug

    mock_fsm_context_step3.clear.assert_called_once()

    log_step3 = integration_session.exec(
        select(Log).where(Log.user_id == db_user.id, Log.command == "subscribe_confirm")
    ).first()  # Предполагаем, что это последний лог такого типа
    assert log_step3 is not None
    assert log_step3.details == f"Type: {INFO_TYPE_EVENTS}, City: {city_input_by_user} (slug: {expected_location_slug}), Freq: {default_frequency}"