# Файл tests/integration/test_subscription_flow.py

import pytest
import html
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from typing import Optional

from sqlmodel import Session, select

from app.bot.main import (
    process_subscribe_command_start,
    process_info_type_choice,
    process_city_for_weather_subscription,
    process_city_for_events_subscription,
    process_frequency_choice,
    SubscriptionStates,
    callback_fsm_cancel_process,
    cmd_cancel_any_state,
)
from app.config import settings as app_settings
from app.database.models import Log, User as DBUser, Subscription
from app.database.crud import create_user, get_subscription_by_user_and_type
from app.bot.constants import (
    INFO_TYPE_NEWS,
    INFO_TYPE_WEATHER,
    INFO_TYPE_EVENTS,
    KUDAGO_LOCATION_SLUGS,
)
from aiogram.types import (
    Message,
    User as AiogramUser,
    Chat,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardRemove  # Для проверки удаления клавиатуры
from tests.utils.mock_helpers import (
    get_mock_fsm_context,
    get_mock_session_context_manager,
)


# Вспомогательная функция для создания mock FSMContext
async def get_mock_fsm_context(
    initial_state: Optional[SubscriptionStates] = None,
    initial_data: Optional[dict] = None,
) -> FSMContext:
    """Создает и возвращает мок FSMContext с MemoryStorage."""
    storage = MemoryStorage()
    state = FSMContext(
        storage=storage, key=MagicMock(chat_id=123, user_id=123, bot_id=42)
    )
    if initial_state:
        await state.set_state(initial_state)
    if initial_data:
        await state.set_data(initial_data)
    return state


def get_mock_session_context_manager(session: Session) -> MagicMock:
    """Создает и возвращает мок контекстного менеджера для сессии."""
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = session
    mock_cm.__exit__.return_value = None
    return mock_cm


@pytest.mark.asyncio
async def test_subscribe_to_news_successful_flow(integration_session: Session):
    """Интеграционный тест: успешная подписка на новости."""
    telegram_user_id = 777001
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    # Step 1: /subscribe
    fsm_context = await get_mock_fsm_context()
    mock_msg_start = AsyncMock(spec=Message, from_user=MagicMock(id=telegram_user_id))
    mock_msg_start.answer = AsyncMock()
    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_subscribe_command_start(mock_msg_start, fsm_context)
    mock_msg_start.answer.assert_called_once()
    assert await fsm_context.get_state() == SubscriptionStates.choosing_info_type

    # Step 2: Choose news
    cb_type = AsyncMock(
        spec=CallbackQuery,
        from_user=MagicMock(id=telegram_user_id),
        data=f"subscribe_type:{INFO_TYPE_NEWS}",
    )
    cb_type.message = AsyncMock(spec=Message)
    cb_type.message.edit_text = AsyncMock()
    cb_type.answer = AsyncMock()
    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_info_type_choice(cb_type, fsm_context)

    # Step 3: Choose frequency
    cb_freq = AsyncMock(
        spec=CallbackQuery,
        from_user=MagicMock(id=telegram_user_id),
        data="frequency:24",
    )
    cb_freq.message = AsyncMock(spec=Message)
    cb_freq.message.edit_text = AsyncMock()
    cb_freq.answer = AsyncMock()
    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_frequency_choice(cb_freq, fsm_context)

    # Final check
    final_sub = integration_session.exec(
        select(Subscription).where(Subscription.user_id == db_user.id)
    ).one()
    assert final_sub.info_type == INFO_TYPE_NEWS
    assert final_sub.frequency == 24
    assert await fsm_context.get_state() is None


@pytest.mark.asyncio
async def test_subscribe_to_news_already_subscribed_flow(integration_session: Session):
    """Интеграционный тест: попытка подписки на новости, когда пользователь уже подписан."""
    telegram_user_id = 777002
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)
    integration_session.add(
        Subscription(
            user_id=db_user.id,
            info_type=INFO_TYPE_NEWS,
            frequency=24,
            status="active",
        )
    )
    integration_session.commit()

    fsm_context = await get_mock_fsm_context(
        initial_state=SubscriptionStates.choosing_info_type
    )
    mock_callback = AsyncMock(
        spec=CallbackQuery,
        from_user=MagicMock(id=telegram_user_id),
        data=f"subscribe_type:{INFO_TYPE_NEWS}",
    )
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()

    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_info_type_choice(mock_callback, fsm_context)

    mock_callback.message.edit_text.assert_called_once_with(
        "Вы уже подписаны на 'Новости'.\n"
        "Для управления подписками используйте /mysubscriptions."
    )
    assert await fsm_context.get_state() is None


@pytest.mark.asyncio
async def test_subscribe_to_weather_successful_flow(integration_session: Session):
    """Интеграционный тест: успешная подписка на погоду."""
    telegram_user_id = 777003
    city = "Лондон"
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)
    fsm_context = await get_mock_fsm_context()

    # Step 1: /subscribe
    mock_msg_start = AsyncMock(spec=Message, from_user=MagicMock(id=telegram_user_id))
    mock_msg_start.answer = AsyncMock()
    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_subscribe_command_start(mock_msg_start, fsm_context)

    # Step 2: Choose weather
    cb_type = AsyncMock(
        spec=CallbackQuery,
        from_user=MagicMock(id=telegram_user_id),
        data=f"subscribe_type:{INFO_TYPE_WEATHER}",
    )
    cb_type.message = AsyncMock(spec=Message)
    cb_type.message.edit_text = AsyncMock()
    cb_type.answer = AsyncMock()
    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_info_type_choice(cb_type, fsm_context)

    # Step 3: Enter city
    msg_city = AsyncMock(
        spec=Message, from_user=MagicMock(id=telegram_user_id), text=city
    )
    msg_city.answer = AsyncMock()
    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_city_for_weather_subscription(msg_city, fsm_context)

    # Step 4: Choose frequency
    cb_freq = AsyncMock(
        spec=CallbackQuery,
        from_user=MagicMock(id=telegram_user_id),
        data="frequency:24",
    )
    cb_freq.message = AsyncMock(spec=Message)
    cb_freq.message.edit_text = AsyncMock()
    cb_freq.answer = AsyncMock()
    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_frequency_choice(cb_freq, fsm_context)

    # Final check
    final_sub = integration_session.exec(
        select(Subscription).where(Subscription.user_id == db_user.id)
    ).one()
    assert final_sub.info_type == INFO_TYPE_WEATHER
    assert final_sub.frequency == 24
    assert final_sub.details == city
    assert await fsm_context.get_state() is None


@pytest.mark.asyncio
async def test_subscribe_to_events_successful_flow(integration_session: Session):
    """Интеграционный тест: успешная подписка на события."""
    telegram_user_id = 777004
    city = "Москва"
    slug = KUDAGO_LOCATION_SLUGS[city.lower()]
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)
    fsm_context = await get_mock_fsm_context()

    # Step 1: /subscribe
    mock_msg_start = AsyncMock(spec=Message, from_user=MagicMock(id=telegram_user_id))
    mock_msg_start.answer = AsyncMock()
    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_subscribe_command_start(mock_msg_start, fsm_context)

    # Step 2: Choose events
    cb_type = AsyncMock(
        spec=CallbackQuery,
        from_user=MagicMock(id=telegram_user_id),
        data=f"subscribe_type:{INFO_TYPE_EVENTS}",
    )
    cb_type.message = AsyncMock(spec=Message)
    cb_type.message.edit_text = AsyncMock()
    cb_type.answer = AsyncMock()
    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_info_type_choice(cb_type, fsm_context)

    # Step 3: Enter city
    msg_city = AsyncMock(
        spec=Message, from_user=MagicMock(id=telegram_user_id), text=city
    )
    msg_city.answer = AsyncMock()
    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_city_for_events_subscription(msg_city, fsm_context)

    # Step 4: Choose frequency
    cb_freq = AsyncMock(
        spec=CallbackQuery,
        from_user=MagicMock(id=telegram_user_id),
        data="frequency:12",
    )
    cb_freq.message = AsyncMock(spec=Message)
    cb_freq.message.edit_text = AsyncMock()
    cb_freq.answer = AsyncMock()
    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_frequency_choice(cb_freq, fsm_context)

    # Final check
    final_sub = integration_session.exec(
        select(Subscription).where(Subscription.user_id == db_user.id)
    ).one()
    assert final_sub.info_type == INFO_TYPE_EVENTS
    assert final_sub.frequency == 12
    assert final_sub.details == slug
    assert await fsm_context.get_state() is None


@pytest.mark.asyncio
async def test_subscribe_to_events_invalid_city_flow(integration_session: Session):
    """
    Интеграционный тест: пользователь вводит неподдерживаемый город для событий.
    """
    telegram_user_id = 777009
    invalid_city = "Урюпинск"
    create_user(session=integration_session, telegram_id=telegram_user_id)
    mock_fsm_context = await get_mock_fsm_context(
        initial_state=SubscriptionStates.entering_city_events
    )
    mock_message = AsyncMock(
        spec=Message, from_user=MagicMock(id=telegram_user_id), text=invalid_city
    )
    mock_message.reply = AsyncMock()

    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_city_for_events_subscription(mock_message, mock_fsm_context)

    supported_cities_text = ", ".join(
        [c.capitalize() for c in KUDAGO_LOCATION_SLUGS.keys()]
    )
    mock_message.reply.assert_called_once_with(
        f"К сожалению, не знаю событий для города '{html.escape(invalid_city)}'...\n"
        f"Попробуйте: {supported_cities_text}..."
    )
    assert await mock_fsm_context.get_state() == SubscriptionStates.entering_city_events


@pytest.mark.asyncio
async def test_subscribe_to_weather_empty_city_input_flow(integration_session: Session):
    """
    Интеграционный тест: пользователь вводит пустое название города для погоды.
    """
    telegram_user_id = 777010
    create_user(session=integration_session, telegram_id=telegram_user_id)
    mock_fsm_context = await get_mock_fsm_context(
        initial_state=SubscriptionStates.entering_city_weather
    )
    mock_message = AsyncMock(
        spec=Message, from_user=MagicMock(id=telegram_user_id), text="  "
    )
    mock_message.reply = AsyncMock()

    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_city_for_weather_subscription(mock_message, mock_fsm_context)

    mock_message.reply.assert_called_once_with(
        "Название города не может быть пустым..."
    )
    assert (
        await mock_fsm_context.get_state() == SubscriptionStates.entering_city_weather
    )


@pytest.mark.asyncio
async def test_cancel_subscription_at_type_choice_by_command(integration_session: Session,):
    """
    Интеграционный тест: отмена процесса подписки командой /cancel на этапе выбора типа информации.
    """
    telegram_user_id = 777011

    # --- Шаг 0: Создаем пользователя ---
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    # --- Шаг 1: Пользователь отправляет команду /subscribe ---
    mock_message_subscribe = AsyncMock(spec=Message)
    mock_message_subscribe.from_user = MagicMock(
        spec=AiogramUser, id=telegram_user_id, full_name="CancelAtType User"
    )
    mock_message_subscribe.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message_subscribe.answer = AsyncMock()

    mock_fsm_context_step1 = await get_mock_fsm_context()
    mock_fsm_context_step1.set_state = AsyncMock()  # Мокируем для проверки вызова

    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_subscribe_command_start(
            mock_message_subscribe, mock_fsm_context_step1
        )

    # Минимальные проверки для Шага 1
    mock_message_subscribe.answer.assert_called_once()
    mock_fsm_context_step1.set_state.assert_called_once_with(
        SubscriptionStates.choosing_info_type
    )

    # --- Шаг 2: Пользователь отправляет команду /cancel ---
    mock_message_cancel = AsyncMock(spec=Message)
    mock_message_cancel.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id)
    mock_message_cancel.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message_cancel.answer = AsyncMock()

    # FSMContext для этого шага должен быть в состоянии choosing_info_type
    mock_fsm_context_step2 = await get_mock_fsm_context(
        initial_state=SubscriptionStates.choosing_info_type
    )
    # Мокируем get_state, чтобы он возвращал текущее состояние для cmd_cancel_any_state
    mock_fsm_context_step2.get_state = AsyncMock(
        return_value=SubscriptionStates.choosing_info_type.state
    )
    mock_fsm_context_step2.clear = AsyncMock()  # Мокируем для проверки очистки

    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await cmd_cancel_any_state(mock_message_cancel, mock_fsm_context_step2)

    # Проверки для Шага 2
    mock_message_cancel.answer.assert_called_once_with(
        "Действие отменено.", reply_markup=ReplyKeyboardRemove()
    )
    mock_fsm_context_step2.clear.assert_called_once()

    # Проверка лога для шага 2 (отмена)
    log_step2_cancel = integration_session.exec(
        select(Log)
        .where(Log.user_id == db_user.id)
        .where(Log.command == "/cancel")
        .order_by(Log.timestamp.desc())
    ).first()
    assert log_step2_cancel is not None
    assert (
        log_step2_cancel.details
        == f"State before cancel: {SubscriptionStates.choosing_info_type.state}"
    )


@pytest.mark.asyncio
async def test_subscribe_command_start_max_subscriptions_reached(
    integration_session: Session,
):
    """
    Интеграционный тест: попытка начать подписку при достижении лимита (3).
    """
    telegram_user_id = 777010
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)
    # Создаем 3 активные подписки
    integration_session.add_all(
        [
            Subscription(user_id=db_user.id, info_type=INFO_TYPE_NEWS, frequency=24),
            Subscription(
                user_id=db_user.id,
                info_type=INFO_TYPE_WEATHER,
                details="Москва",
                frequency=24,
            ),
            Subscription(
                user_id=db_user.id,
                info_type=INFO_TYPE_EVENTS,
                details="msk",
                frequency=24,
            ),
        ]
    )
    integration_session.commit()

    fsm_context = await get_mock_fsm_context()
    mock_message = AsyncMock(spec=Message, from_user=MagicMock(id=telegram_user_id))
    mock_message.answer = AsyncMock()

    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_subscribe_command_start(mock_message, fsm_context)

    # Проверяем, что бот ответил об ошибке и состояние не изменилось
    mock_message.answer.assert_called_once_with(
        "У вас уже 3 активных подписки. Это максимальное количество.\n"
        "Вы можете удалить одну из существующих подписок с помощью /unsubscribe."
    )
    assert await fsm_context.get_state() is None


@pytest.mark.asyncio
async def test_subscribe_to_weather_already_subscribed_flow(
    integration_session: Session,
):
    """
    Интеграционный тест: попытка подписки на погоду в городе, на который уже есть подписка.
    """
    telegram_user_id = 777011
    city = "Париж"
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)
    # Создаем существующую подписку на погоду
    integration_session.add(
        Subscription(
            user_id=db_user.id,
            info_type=INFO_TYPE_WEATHER,
            details=city,
            frequency=24,
        )
    )
    integration_session.commit()

    # Устанавливаем FSM в состояние ввода города
    fsm_context = await get_mock_fsm_context(
        initial_state=SubscriptionStates.entering_city_weather
    )
    mock_message = AsyncMock(
        spec=Message, from_user=MagicMock(id=telegram_user_id), text=city
    )
    mock_message.answer = AsyncMock()

    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_city_for_weather_subscription(mock_message, fsm_context)

    # Проверяем, что бот ответил об ошибке и состояние сбросилось
    mock_message.answer.assert_called_once_with(
        f"Вы уже подписаны на '{INFO_TYPE_WEATHER}' для города '{html.escape(city)}'."
    )
    assert await fsm_context.get_state() is None


@pytest.mark.asyncio
async def test_subscribe_to_events_already_subscribed_flow(
    integration_session: Session,
):
    """
    Интеграционный тест: попытка подписки на события в городе, на который уже есть подписка.
    """
    telegram_user_id = 777012
    city_input = "спб"
    city_slug = KUDAGO_LOCATION_SLUGS[city_input]
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)
    # Создаем существующую подписку на события
    integration_session.add(
        Subscription(
            user_id=db_user.id,
            info_type=INFO_TYPE_EVENTS,
            details=city_slug,
            frequency=12,
        )
    )
    integration_session.commit()

    # Устанавливаем FSM в состояние ввода города
    fsm_context = await get_mock_fsm_context(
        initial_state=SubscriptionStates.entering_city_events
    )
    mock_message = AsyncMock(
        spec=Message, from_user=MagicMock(id=telegram_user_id), text=city_input
    )
    mock_message.answer = AsyncMock()

    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await process_city_for_events_subscription(mock_message, fsm_context)

    # Проверяем, что бот ответил об ошибке и состояние сбросилось
    mock_message.answer.assert_called_once_with(
        f"Вы уже подписаны на '{INFO_TYPE_EVENTS}' для города '{html.escape(city_input)}'."
    )
    assert await fsm_context.get_state() is None


@pytest.mark.asyncio
async def test_cancel_subscription_at_type_choice_by_button(
    integration_session: Session,
):
    """
    Интеграционный тест: отмена процесса подписки кнопкой "Отмена" на шаге выбора типа.
    """
    telegram_user_id = 777009
    create_user(session=integration_session, telegram_id=telegram_user_id)
    fsm_context = await get_mock_fsm_context(
        initial_state=SubscriptionStates.choosing_info_type
    )

    mock_callback = AsyncMock(
        spec=CallbackQuery,
        from_user=MagicMock(id=telegram_user_id),
        data="subscribe_fsm_cancel",
    )
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()

    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await callback_fsm_cancel_process(mock_callback, fsm_context)

    # Проверяем, что состояние сброшено и было отправлено подтверждение
    assert await fsm_context.get_state() is None
    mock_callback.message.edit_text.assert_called_once_with("Процесс подписки отменен.")
    mock_callback.answer.assert_called_once()

    # Проверяем запись в лог
    log = integration_session.exec(
        select(Log).where(Log.command == "subscribe_fsm_cancel")
    ).one()
    assert log.details == "Cancelled type choice by button"


@pytest.mark.asyncio
async def test_cancel_subscription_at_city_input_by_command(
    integration_session: Session,
):
    """
    Интеграционный тест: отмена процесса подписки командой /cancel на шаге ввода города.
    """
    telegram_user_id = 777013
    create_user(session=integration_session, telegram_id=telegram_user_id)
    fsm_context = await get_mock_fsm_context(
        initial_state=SubscriptionStates.entering_city_weather
    )

    mock_message = AsyncMock(spec=Message, from_user=MagicMock(id=telegram_user_id))
    mock_message.answer = AsyncMock()

    with patch(
        "app.bot.main.get_session",
        return_value=get_mock_session_context_manager(integration_session),
    ):
        await cmd_cancel_any_state(mock_message, fsm_context)

    # Проверяем, что состояние сброшено и было отправлено подтверждение
    assert await fsm_context.get_state() is None
    mock_message.answer.assert_called_once_with(
        "Действие отменено.", reply_markup=ReplyKeyboardRemove()
    )

    # Проверяем запись в лог
    log = integration_session.exec(
        select(Log)
        .where(Log.command == "/cancel")
        .where(
            Log.user_id == 1
        )  # Предполагая, что это первый созданный юзер в этой сессии
    ).one()
    assert (
        log.details
        == f"State before cancel: {SubscriptionStates.entering_city_weather.state}"
    )
