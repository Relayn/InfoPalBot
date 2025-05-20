import pytest
import html
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.bot.main import (
    process_mysubscriptions_command,
    process_unsubscribe_command_start,
    process_unsubscribe_confirm,
    process_unsubscribe_action_cancel,
    SubscriptionStates,
    INFO_TYPE_WEATHER,
    INFO_TYPE_NEWS,
    INFO_TYPE_EVENTS,
    KUDAGO_LOCATION_SLUGS
)
from app.database.models import User as DBUser, Subscription as DBSubscription
from aiogram.types import Message, User as AiogramUser, Chat, CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
# Убираем импорты CRUD, так как мы их патчим по месту вызова в app.bot.main

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
    engine = create_engine("sqlite:///:memory:", echo=False, connect_args={"check_same_thread": False})
    from app.database import models # noqa
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

# --- Тесты для process_mysubscriptions_command ---
@pytest.mark.asyncio
async def test_process_mysubscriptions_command_no_user_sub(session_sub):
    mock_message = AsyncMock(spec=Message); mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=777)
    # Мокаем get_session так, чтобы он возвращал контекстный менеджер, который дает нашу session_sub
    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = session_sub
    with patch('app.bot.main.get_session') as mock_get_session_cm_object, \
            patch('app.bot.main.get_user_by_telegram_id', return_value=None) as mock_get_user, \
            patch('app.bot.main.log_user_action') as mock_log_action:  # Мокируем log_user_action
        mock_generator = MagicMock()
        mock_session_context_manager = MagicMock()  # Определяем здесь
        mock_session_context_manager.__enter__.return_value = session_sub
        mock_generator.__next__.return_value = mock_session_context_manager
        mock_get_session_cm_object.return_value = mock_generator

        await process_mysubscriptions_command(mock_message)

        # Проверяем, что get_user_by_telegram_id был вызван (один раз из самого хендлера)
        mock_get_user.assert_called_once_with(session=session_sub, telegram_id=777)
        # Проверяем, что log_user_action тоже был вызван
        mock_log_action.assert_called_once()
        mock_message.answer.assert_called_once_with("Не удалось найти информацию о вас...")

@pytest.mark.asyncio
async def test_process_mysubscriptions_command_no_subscriptions_sub(db_user_sub, session_sub):
    mock_message = AsyncMock(spec=Message); mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=db_user_sub.telegram_id)
    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = session_sub
    with patch('app.bot.main.get_session', return_value=mock_session_context_manager) as mock_get_session_cm_object, \
         patch('app.bot.main.get_user_by_telegram_id', return_value=db_user_sub), \
         patch('app.bot.main.get_subscriptions_by_user_id', return_value=[]) as mock_get_subs:
        mock_generator = MagicMock()
        mock_generator.__next__.return_value = mock_session_context_manager
        mock_get_session_cm_object.return_value = mock_generator

        await process_mysubscriptions_command(mock_message)
        mock_get_subs.assert_called_once_with(session=session_sub, user_id=db_user_sub.id)
        mock_message.answer.assert_called_once_with("У вас пока нет активных подписок...")

@pytest.mark.asyncio
async def test_process_mysubscriptions_command_with_subscriptions_sub(db_user_sub, session_sub):
    mock_message = AsyncMock(spec=Message); mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=db_user_sub.telegram_id)
    sub1 = DBSubscription(id=1, user_id=db_user_sub.id, info_type=INFO_TYPE_NEWS, frequency="daily", details=None, status="active")
    sub2 = DBSubscription(id=2, user_id=db_user_sub.id, info_type=INFO_TYPE_WEATHER, frequency="daily", details="Москва", status="active")
    sub3 = DBSubscription(id=3, user_id=db_user_sub.id, info_type=INFO_TYPE_EVENTS, frequency="daily", details="msk", status="active")
    mock_subs_list = [sub1, sub2, sub3]
    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = session_sub
    with patch('app.bot.main.get_session', return_value=mock_session_context_manager) as mock_get_session_cm_object, \
         patch('app.bot.main.get_user_by_telegram_id', return_value=db_user_sub), \
         patch('app.bot.main.get_subscriptions_by_user_id', return_value=mock_subs_list) as mock_get_user_subs_patched:
        mock_generator = MagicMock()
        mock_generator.__next__.return_value = mock_session_context_manager
        mock_get_session_cm_object.return_value = mock_generator

        await process_mysubscriptions_command(mock_message)
        mock_get_user_subs_patched.assert_called_once_with(session=mock_session_context_manager.__enter__.return_value, user_id=db_user_sub.id)
        expected_lines = [
            "<b>📋 Ваши активные подписки:</b>",
            f"1. Новости (Россия) ({html.escape(sub1.frequency or 'ежедн.')})",
            f"2. Погода для города: <b>{html.escape(sub2.details)}</b> ({html.escape(sub2.frequency or 'ежедн.')})",
            f"3. События в городе: <b>{html.escape('Москва')}</b> ({html.escape(sub3.frequency or 'ежедн.')})"
        ]
        expected_text = "\n".join(expected_lines)
        mock_message.answer.assert_called_once_with(expected_text)

# --- Тесты для /unsubscribe ---
@pytest.mark.asyncio
async def test_process_unsubscribe_command_start_no_subscriptions_sub(db_user_sub, session_sub):
    mock_message = AsyncMock(spec=Message); mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=db_user_sub.telegram_id)
    mock_state = AsyncMock(spec=FSMContext)
    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = session_sub
    with patch('app.bot.main.get_session', return_value=mock_session_context_manager) as mock_get_session_cm_object, \
         patch('app.bot.main.get_user_by_telegram_id', return_value=db_user_sub), \
         patch('app.bot.main.get_subscriptions_by_user_id', return_value=[]):
        mock_generator = MagicMock()
        mock_generator.__next__.return_value = mock_session_context_manager
        mock_get_session_cm_object.return_value = mock_generator
        await process_unsubscribe_command_start(mock_message, mock_state)
        mock_message.answer.assert_called_once_with("У вас нет активных подписок для отмены.")

@pytest.mark.asyncio
async def test_process_unsubscribe_command_start_with_subscriptions_sub(db_user_sub, session_sub):
    mock_message = AsyncMock(spec=Message); mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=db_user_sub.telegram_id)
    mock_state = AsyncMock(spec=FSMContext)
    sub1 = DBSubscription(id=10, user_id=db_user_sub.id, info_type=INFO_TYPE_WEATHER, frequency="daily", details="Сочи", status="active")
    mock_subs_list = [sub1]
    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = session_sub
    with patch('app.bot.main.get_session', return_value=mock_session_context_manager) as mock_get_session_cm_object, \
         patch('app.bot.main.get_user_by_telegram_id', return_value=db_user_sub), \
         patch('app.bot.main.get_subscriptions_by_user_id', return_value=mock_subs_list):
        mock_generator = MagicMock()
        mock_generator.__next__.return_value = mock_session_context_manager
        mock_get_session_cm_object.return_value = mock_generator
        await process_unsubscribe_command_start(mock_message, mock_state)
        args, kwargs = mock_message.answer.call_args
        assert args[0] == "Выберите подписку, от которой хотите отписаться:"
        reply_markup = kwargs['reply_markup']
        assert isinstance(reply_markup, InlineKeyboardMarkup)
        assert "Погода: Сочи" in reply_markup.inline_keyboard[0][0].text

@pytest.mark.asyncio
async def test_process_unsubscribe_confirm_success_sub(db_user_sub, session_sub):
    mock_callback_query = AsyncMock(spec=CallbackQuery); mock_callback_query.answer = AsyncMock()
    mock_callback_query.message = AsyncMock(spec=Message); mock_callback_query.message.edit_text = AsyncMock()
    mock_callback_query.from_user = MagicMock(spec=AiogramUser, id=db_user_sub.telegram_id)
    sub_to_delete = DBSubscription(user_id=db_user_sub.id, info_type=INFO_TYPE_NEWS, frequency="daily", status="active")
    session_sub.add(sub_to_delete); session_sub.commit(); session_sub.refresh(sub_to_delete)
    mock_callback_query.data = f"unsubscribe_confirm:{sub_to_delete.id}"
    mock_state = AsyncMock(spec=FSMContext)
    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = session_sub # Эта сессия теперь содержит sub_to_delete
    with patch('app.bot.main.get_session', return_value=mock_session_context_manager) as mock_get_session_cm_object, \
         patch('app.bot.main.get_user_by_telegram_id', return_value=db_user_sub), \
         patch('app.bot.main.delete_subscription', return_value=True) as mock_delete_sub_patched:
        mock_generator = MagicMock()
        mock_generator.__next__.return_value = mock_session_context_manager
        mock_get_session_cm_object.return_value = mock_generator
        await process_unsubscribe_confirm(mock_callback_query, mock_state)
        mock_delete_sub_patched.assert_called_once_with(session=session_sub, subscription_id=sub_to_delete.id)
        mock_callback_query.message.edit_text.assert_called_once_with("Вы успешно отписались.")

@pytest.mark.asyncio
async def test_process_unsubscribe_confirm_not_users_subscription_sub(db_user_sub, session_sub):
    mock_callback_query = AsyncMock(spec=CallbackQuery); mock_callback_query.answer = AsyncMock()
    mock_callback_query.message = AsyncMock(spec=Message); mock_callback_query.message.edit_text = AsyncMock()
    mock_callback_query.from_user = MagicMock(spec=AiogramUser, id=db_user_sub.telegram_id)
    other_user_sub_id = 21
    other_user_sub_instance = DBSubscription(id=other_user_sub_id, user_id=999, info_type=INFO_TYPE_NEWS, frequency="daily", status="active")
    mock_callback_query.data = f"unsubscribe_confirm:{other_user_sub_id}"
    mock_state = AsyncMock(spec=FSMContext)
    # Мокируем session.get, чтобы он вернул подписку другого пользователя
    mock_session_for_get = MagicMock(spec=session_sub)
    mock_session_for_get.get.return_value = other_user_sub_instance
    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = mock_session_for_get
    with patch('app.bot.main.get_session', return_value=mock_session_context_manager) as mock_get_session_cm_object, \
         patch('app.bot.main.get_user_by_telegram_id', return_value=db_user_sub), \
         patch('app.bot.main.delete_subscription') as mock_delete_sub_patched:
        mock_generator = MagicMock()
        mock_generator.__next__.return_value = mock_session_context_manager
        mock_get_session_cm_object.return_value = mock_generator
        await process_unsubscribe_confirm(mock_callback_query, mock_state)
        mock_delete_sub_patched.assert_not_called()
        mock_callback_query.message.edit_text.assert_called_once_with("Ошибка: это не ваша подписка или она не найдена.")

@pytest.mark.asyncio
async def test_process_unsubscribe_action_cancel_sub():
    mock_callback_query = AsyncMock(spec=CallbackQuery); mock_callback_query.answer = AsyncMock()
    mock_callback_query.message = AsyncMock(spec=Message); mock_callback_query.message.edit_text = AsyncMock()
    mock_callback_query.from_user = MagicMock(spec=AiogramUser, id=123)
    mock_callback_query.data = "unsubscribe_action_cancel"
    mock_state = AsyncMock(spec=FSMContext)
    with patch('app.bot.main.logger'): # Просто патчим логгер, чтобы не было ошибок
        await process_unsubscribe_action_cancel(mock_callback_query, mock_state)
        mock_callback_query.message.edit_text.assert_called_once_with("Операция отписки отменена.")