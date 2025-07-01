import pytest
import html
from unittest.mock import AsyncMock, MagicMock, patch, call, ANY

from app.bot.handlers.subscription import (
    process_subscribe_command_start,
    process_frequency_choice,
    process_mysubscriptions_command,
    process_unsubscribe_command_start,
    process_unsubscribe_confirm,
    process_unsubscribe_action_cancel,
)
from app.bot.fsm import SubscriptionStates
from app.bot.constants import INFO_TYPE_WEATHER, INFO_TYPE_NEWS, INFO_TYPE_EVENTS
from app.database.models import User as DBUser, Subscription as DBSubscription
from aiogram.types import Message, User as AiogramUser, Chat, CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from sqlmodel import Session, select
from tests.utils.mock_helpers import get_mock_fsm_context
from tests.utils.mock_helpers import get_mock_session_context_manager


@pytest.fixture(name="engine_sub")
def engine_fixture_sub():
    from sqlmodel import create_engine, SQLModel
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if dbapi_connection.__class__.__module__ == "sqlite3":
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    engine = create_engine(
        "sqlite:///:memory:", echo=False, connect_args={"check_same_thread": False}
    )
    from app.database import models as db_models  # noqa

    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session_sub")
def session_fixture_sub(engine_sub):
    from sqlmodel import Session

    with Session(engine_sub) as session:
        yield session


@pytest.fixture
def db_user_sub(session_sub) -> DBUser:
    from app.database.crud import create_user

    user = create_user(session=session_sub, telegram_id=789789)
    return user


@pytest.mark.asyncio
@patch("app.bot.handlers.subscription.db_create_subscription")
@patch("app.bot.handlers.subscription.scheduler")
async def test_process_frequency_choice_cron_success(mock_scheduler, mock_db_create, db_user_sub, session_sub):
    """Тест: успешное создание cron-подписки."""
    telegram_id = db_user_sub.telegram_id
    mock_callback = AsyncMock(spec=CallbackQuery, from_user=MagicMock(id=telegram_id), data="cron:09:00")
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()
    fsm_context = await get_mock_fsm_context(
        initial_state=SubscriptionStates.choosing_frequency,
        initial_data={"info_type": INFO_TYPE_NEWS, "details": None},
    )
    # Мок созданной подписки
    mock_subscription = DBSubscription(id=99, user_id=db_user_sub.id, cron_expression="0 9 * * *")
    mock_db_create.return_value = mock_subscription

    with patch("app.bot.handlers.subscription.get_session",
               return_value=MagicMock(__enter__=MagicMock(return_value=session_sub))), \
            patch("app.bot.handlers.subscription.get_user_by_telegram_id", return_value=db_user_sub), \
            patch("app.bot.handlers.subscription.log_user_action"):
        await process_frequency_choice(mock_callback, fsm_context)

        # Проверяем, что подписка создается с cron_expression
        mock_db_create.assert_called_once_with(
            session=session_sub,
            user_id=db_user_sub.id,
            info_type=INFO_TYPE_NEWS,
            details=None,
            category=None,
            cron_expression="0 9 * * *",
        )
        # Проверяем, что задача добавляется с cron-триггером
        mock_scheduler.add_job.assert_called_once()
        _, kwargs = mock_scheduler.add_job.call_args
        assert kwargs["trigger"] == "cron"
        assert kwargs["hour"] == 9
        assert kwargs["minute"] == 0
        assert kwargs["id"] == "sub_99"

        mock_callback.message.edit_text.assert_called_once_with("Вы успешно подписались!")


@pytest.mark.asyncio
async def test_process_mysubscriptions_command_with_mixed_subscriptions(db_user_sub, session_sub):
    """Тест: /mysubscriptions корректно отображает подписки с категориями и без."""
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=db_user_sub.telegram_id)

    # Создаем подписки разных типов
    sub1 = DBSubscription(id=1, user_id=db_user_sub.id, info_type=INFO_TYPE_WEATHER, details="Москва", frequency=12)
    sub2 = DBSubscription(id=2, user_id=db_user_sub.id, info_type=INFO_TYPE_NEWS, cron_expression="0 9 * * *", category="technology")
    sub3 = DBSubscription(id=3, user_id=db_user_sub.id, info_type=INFO_TYPE_EVENTS, details="spb", frequency=6, category=None) # Категория "все"

    with patch("app.bot.handlers.subscription.get_session",
               return_value=MagicMock(__enter__=MagicMock(return_value=session_sub))), \
            patch("app.bot.handlers.subscription.get_user_by_telegram_id", return_value=db_user_sub), \
            patch("app.bot.handlers.subscription.get_subscriptions_by_user_id", return_value=[sub1, sub2, sub3]), \
            patch("app.bot.handlers.subscription.log_user_action"):
        await process_mysubscriptions_command(mock_message)

        args, _ = mock_message.answer.call_args
        response_text = args[0]

        assert "Погода: <b>Москва</b>" in response_text
        assert "Новости (США) (technology)" in response_text
        assert "События: <b>Санкт-петербург</b> (все)" in response_text

@pytest.mark.asyncio
async def test_subscribe_start_limit_reached(db_user_sub, session_sub):
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=db_user_sub.telegram_id)
    mock_state = await get_mock_fsm_context()
    mock_subs = [MagicMock(), MagicMock(), MagicMock()]
    mock_session_cm = MagicMock()
    mock_session_cm.__enter__.return_value = session_sub
    mock_session_cm.__exit__.return_value = None
    with patch("app.bot.handlers.subscription.get_session", return_value=mock_session_cm), patch(
            "app.bot.handlers.subscription.get_user_by_telegram_id", return_value=db_user_sub), patch(
            "app.bot.handlers.subscription.get_subscriptions_by_user_id", return_value=mock_subs), patch(
            "app.bot.handlers.subscription.log_user_action"):
        await process_subscribe_command_start(mock_message, mock_state)
        expected_text = (
            "У вас уже 3 активных подписки. Это максимальное количество.\n" "Вы можете удалить одну из существующих подписок с помощью /unsubscribe.")
        mock_message.answer.assert_called_once_with(expected_text)


@pytest.mark.asyncio
async def test_process_city_search_too_short_query():
    """Тест: пользователь вводит слишком короткий запрос для поиска города."""
    mock_message = AsyncMock(spec=Message, text="Мс")
    mock_message.answer = AsyncMock()
    mock_state = await get_mock_fsm_context(
        initial_state=SubscriptionStates.prompting_city_search
    )

    from app.bot.handlers.subscription import process_city_search

    await process_city_search(mock_message, mock_state)

    mock_message.answer.assert_called_once_with(
        "Пожалуйста, введите минимум 3 буквы для поиска."
    )
    assert await mock_state.get_state() == SubscriptionStates.prompting_city_search


@pytest.mark.asyncio
async def test_process_city_search_found_cities():
    """Тест: успешный поиск городов и предложение выбора."""
    mock_message = AsyncMock(spec=Message, text="Мос")
    mock_message.answer = AsyncMock()
    mock_state = await get_mock_fsm_context(
        initial_state=SubscriptionStates.prompting_city_search
    )

    from app.bot.handlers.subscription import process_city_search

    with patch(
        "app.bot.handlers.subscription.get_city_selection_keyboard"
    ) as mock_get_keyboard:
        await process_city_search(mock_message, mock_state)

        mock_get_keyboard.assert_called_once_with(["Москва"])
        mock_message.answer.assert_called_once()
        assert await mock_state.get_state() == SubscriptionStates.choosing_city_from_list


@pytest.mark.asyncio
async def test_process_city_selection_for_weather_success():
    """Тест: успешный выбор города для подписки на погоду."""
    selected_city = "Казань"
    telegram_id = 789789
    mock_callback = AsyncMock(
        spec=CallbackQuery,
        data=f"city_select:{selected_city}",
        from_user=MagicMock(id=telegram_id),
    )
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()
    mock_state = await get_mock_fsm_context(
        initial_state=SubscriptionStates.choosing_city_from_list,
        initial_data={"info_type": INFO_TYPE_WEATHER, "category": None},
    )

    from app.bot.handlers.subscription import process_city_selection

    with patch("app.bot.handlers.subscription.get_session"), patch(
        "app.bot.handlers.subscription.get_user_by_telegram_id",
        return_value=MagicMock(id=1),
    ), patch(
        "app.bot.handlers.subscription.get_subscription_by_user_and_type",
        return_value=None,
    ):
        await process_city_selection(mock_callback, mock_state)

        # 1. Проверяем, что данные в FSM обновились корректно
        state_data = await mock_state.get_data()
        assert state_data["details"] == selected_city

        # 2. Проверяем, что бот ответил пользователю
        mock_callback.message.edit_text.assert_called_once()

        # 3. Проверяем, что состояние FSM переключилось на следующее
        assert await mock_state.get_state() == SubscriptionStates.choosing_frequency

@pytest.mark.asyncio
async def test_process_city_search_no_cities_found():
    """Тест: поиск города не дал результатов."""
    mock_message = AsyncMock(spec=Message, text="НесуществующийГород123")
    mock_message.answer = AsyncMock()
    mock_state = await get_mock_fsm_context(
        initial_state=SubscriptionStates.prompting_city_search
    )

    from app.bot.handlers.subscription import process_city_search

    await process_city_search(mock_message, mock_state)

    mock_message.answer.assert_called_once_with(
        "К сожалению, по вашему запросу ничего не найдено. Попробуйте еще раз."
    )
    # Состояние не должно измениться
    assert await mock_state.get_state() == SubscriptionStates.prompting_city_search


@pytest.mark.asyncio
async def test_process_city_selection_duplicate_subscription():
    """Тест: пользователь выбирает город, на который уже есть подписка."""
    selected_city = "Москва"
    telegram_id = 111222
    mock_callback = AsyncMock(
        spec=CallbackQuery,
        data=f"city_select:{selected_city}",
        from_user=MagicMock(id=telegram_id)  # <--- ДОБАВЛЕНО
    )
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()
    mock_state = await get_mock_fsm_context(
        initial_data={"info_type": INFO_TYPE_WEATHER}
    )

    from app.bot.handlers.subscription import process_city_selection

    # Имитируем, что подписка найдена
    with patch("app.bot.handlers.subscription.get_session"), patch(
        "app.bot.handlers.subscription.get_user_by_telegram_id",
    ), patch(
        "app.bot.handlers.subscription.get_subscription_by_user_and_type",
        return_value=MagicMock(),
    ):
        await process_city_selection(mock_callback, mock_state)

        mock_callback.message.edit_text.assert_called_once_with(
            "У вас уже есть такая подписка."
        )
        assert await mock_state.get_state() is None  # FSM сбрасывается


@pytest.mark.asyncio
async def test_process_city_selection_unsupported_event_city():
    """Тест: пользователь выбирает город, который не поддерживается для событий."""
    # Город есть в общем списке, но нет в KUDAGO_LOCATION_SLUGS
    unsupported_city = "Ижевск"
    mock_callback = AsyncMock(spec=CallbackQuery, data=f"city_select:{unsupported_city}")
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()
    mock_state = await get_mock_fsm_context(
        initial_data={"info_type": INFO_TYPE_EVENTS}
    )

    from app.bot.handlers.subscription import process_city_selection

    await process_city_selection(mock_callback, mock_state)

    mock_callback.message.edit_text.assert_called_once_with(
        f"К сожалению, город '{html.escape(unsupported_city)}' больше не поддерживается для событий. "
        "Пожалуйста, начните подписку заново с помощью /subscribe."
    )
    assert await mock_state.get_state() is None

@pytest.mark.asyncio
async def test_callback_fsm_cancel_process():
    """Тест: отмена FSM через inline-кнопку."""
    mock_callback = AsyncMock(spec=CallbackQuery)
    mock_callback.from_user = MagicMock(id=123)
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()
    mock_state = await get_mock_fsm_context(
        initial_state=SubscriptionStates.choosing_category
    )

    from app.bot.handlers.subscription import callback_fsm_cancel_process

    mock_session = MagicMock()
    mock_session_cm = get_mock_session_context_manager(mock_session)

    with patch("app.bot.handlers.subscription.get_session", return_value=mock_session_cm):
        await callback_fsm_cancel_process(mock_callback, mock_state)

        mock_callback.message.edit_text.assert_called_once_with(
            "Процесс подписки отменен."
        )
        assert await mock_state.get_state() is None


@pytest.mark.asyncio
async def test_process_city_search_ignores_non_text_message():
    """Тест: обработчик поиска города игнорирует сообщения не-текстового типа."""

    mock_message = AsyncMock(spec=Message)
    mock_message.text = None  # Имитация стикера или фото
    mock_message.answer = AsyncMock()
    mock_state = await get_mock_fsm_context(
        initial_state=SubscriptionStates.prompting_city_search
    )

    from app.bot.handlers.subscription import process_city_search

    await process_city_search(mock_message, mock_state)

    mock_message.answer.assert_not_called()


@pytest.mark.asyncio
@patch("app.bot.handlers.subscription.scheduler")
async def test_process_unsubscribe_confirm_job_not_found(
    mock_scheduler, db_user_sub, session_sub
):
    """
    Тест: отписка проходит успешно, даже если задача в планировщике не найдена.
    """
    telegram_id = db_user_sub.telegram_id
    subscription = DBSubscription(id=555, user_id=db_user_sub.id, info_type="news", frequency=3)
    session_sub.add(subscription)
    session_sub.commit()

    mock_callback = AsyncMock(
        spec=CallbackQuery,
        from_user=MagicMock(id=telegram_id),
        data="unsubscribe_confirm:555",
    )
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()

    mock_scheduler.get_job.return_value = None  # Задача не найдена

    mock_session_cm = get_mock_session_context_manager(session_sub)
    with patch(
        "app.bot.handlers.subscription.get_session", return_value=mock_session_cm
    ), patch("app.bot.handlers.subscription.logger.warning") as mock_logger:
        await process_unsubscribe_confirm(mock_callback, AsyncMock())

        # Проверяем, что подписка все равно деактивирована
        deactivated_sub = session_sub.get(DBSubscription, 555)
        assert deactivated_sub.status == "inactive"

        # Проверяем, что бот сообщил об успехе
        mock_callback.message.edit_text.assert_called_once_with("Вы успешно отписались.")

        # Проверяем, что была залогирована попытка удаления несуществующей задачи
        mock_logger.assert_called_once_with(
            "Задача sub_555 для удаления не найдена в планировщике."
        )

@pytest.mark.asyncio
async def test_process_unsubscribe_action_cancel():
    """Тест: отмена операции отписки."""
    mock_callback = AsyncMock(spec=CallbackQuery)
    mock_callback.from_user = MagicMock(id=123)
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()

    mock_session = MagicMock()
    mock_session_cm = get_mock_session_context_manager(mock_session)

    with patch("app.bot.handlers.subscription.get_session", return_value=mock_session_cm):
        await process_unsubscribe_action_cancel(mock_callback, AsyncMock())

        mock_callback.message.edit_text.assert_called_once_with(
            "Операция отписки отменена."
        )