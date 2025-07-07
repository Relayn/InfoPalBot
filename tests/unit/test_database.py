import pytest
from sqlmodel import create_engine, Session, SQLModel, select
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from app.database.models import User, Subscription, Log
from app.database.crud import (
    get_user_by_telegram_id,
    create_user,
    create_user_if_not_exists,
    create_subscription,
    get_subscriptions_by_user_id,
    get_subscription_by_user_and_type,
    delete_subscription,
    create_log_entry,
    log_user_action, # Добавим импорт для полноты
)

# Фикстуры engine и session
@pytest.fixture(name="engine")
def engine_fixture():
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if dbapi_connection.__class__.__module__ == "sqlite3":
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    engine_instance = create_engine("sqlite:///:memory:", echo=False, connect_args={"check_same_thread": False})
    from app.database import models as db_models
    SQLModel.metadata.create_all(engine_instance)
    yield engine_instance
    SQLModel.metadata.drop_all(engine_instance)

@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session_instance:
        yield session_instance

@pytest.fixture
def db_user(session: Session) -> User:
    user = create_user(session=session, telegram_id=111222)
    return user

# --- Тесты для User CRUD (без изменений) ---
def test_get_user_by_existing_telegram_id(session: Session):
    telegram_id = 12345
    user_to_create = User(telegram_id=telegram_id)
    session.add(user_to_create)
    session.commit(); session.refresh(user_to_create)
    found_user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)
    assert found_user is not None
    assert found_user.telegram_id == telegram_id

# ... (остальные тесты User CRUD без изменений) ...
def test_get_user_by_non_existing_telegram_id(session: Session):
    found_user = get_user_by_telegram_id(session=session, telegram_id=99999)
    assert found_user is None

def test_create_user_successfully(session: Session):
    telegram_id = 54321
    created_user = create_user(session=session, telegram_id=telegram_id)
    assert created_user is not None
    assert created_user.telegram_id == telegram_id
    assert created_user.id is not None
    retrieved_user = session.get(User, created_user.id)
    assert retrieved_user is not None

def test_create_user_with_existing_telegram_id_fails(session: Session):
    telegram_id = 112233
    create_user(session=session, telegram_id=telegram_id)
    with pytest.raises(IntegrityError):
        create_user(session=session, telegram_id=telegram_id)
        session.commit()

def test_create_user_if_not_exists_creates_new(session: Session):
    telegram_id = 67890
    user = create_user_if_not_exists(session=session, telegram_id=telegram_id)
    assert user is not None
    assert user.telegram_id == telegram_id
    assert user.id is not None
    found_user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)
    assert found_user is not None

def test_create_user_if_not_exists_returns_existing(session: Session):
    telegram_id = 98765
    existing_user = create_user(session=session, telegram_id=telegram_id)
    user = create_user_if_not_exists(session=session, telegram_id=telegram_id)
    assert user is not None
    assert user.id == existing_user.id
    statement = select(User).where(User.telegram_id == telegram_id)
    all_users = session.exec(statement).all()
    assert len(all_users) == 1


# --- Тесты для Subscription CRUD (ИЗМЕНЕНО) ---
def test_create_subscription_success_with_frequency(session: Session, db_user: User):
    sub = create_subscription(
        session,
        db_user.id,
        "weather",
        details="Moscow",
        category="rainy",
        frequency=12,
    )
    assert sub is not None
    assert sub.user_id == db_user.id
    assert sub.frequency == 12
    assert sub.category == "rainy"
    assert sub.cron_expression is None

def test_create_subscription_success_with_cron(session: Session, db_user: User):
    cron_expr = "0 9 * * *"
    sub = create_subscription(session, db_user.id, "news", cron_expression=cron_expr)
    assert sub is not None
    assert sub.user_id == db_user.id
    assert sub.cron_expression == cron_expr
    assert sub.frequency is None

def test_create_subscription_fails_with_both_frequency_and_cron(session: Session, db_user: User):
    with pytest.raises(ValueError, match="Нельзя указывать frequency и cron_expression одновременно."):
        create_subscription(session, db_user.id, "events", frequency=6, cron_expression="0 9 * * *")

def test_create_subscription_fails_with_neither_frequency_nor_cron(session: Session, db_user: User):
    with pytest.raises(ValueError, match="Должен быть указан либо frequency, либо cron_expression."):
        create_subscription(session, db_user.id, "weather")

def test_create_subscription_invalid_user_id_fails(session: Session):
    with pytest.raises(IntegrityError):
        create_subscription(session, 99999, "news", frequency=6)

def test_get_subscriptions_by_user_id(session: Session, db_user: User):
    sub1 = create_subscription(session, db_user.id, "news", frequency=24)
    sub2 = create_subscription(session, db_user.id, "weather", details="Kyiv", cron_expression="0 10 * * *")
    inactive_sub = Subscription(user_id=db_user.id, info_type="events", frequency=1, status="inactive")
    session.add(inactive_sub); session.commit()
    subscriptions = get_subscriptions_by_user_id(session, db_user.id)
    assert len(subscriptions) == 2
    assert sub1 in subscriptions
    assert sub2 in subscriptions

# ... (остальные тесты Subscription и Log CRUD без изменений) ...
def test_get_subscriptions_by_user_id_no_subscriptions(session: Session, db_user: User):
    assert len(get_subscriptions_by_user_id(session, db_user.id)) == 0

def test_get_subscription_by_user_and_type_exists(session: Session, db_user: User):
    # Тест с деталями и категорией
    sub1 = create_subscription(session, db_user.id, "events", details="msk", category="concert", frequency=1)
    found1 = get_subscription_by_user_and_type(session, db_user.id, "events", "msk", "concert")
    assert found1 is not None
    assert found1.id == sub1.id

    # Тест без деталей, но с категорией
    sub2 = create_subscription(session, db_user.id, "news", category="technology", frequency=3)
    found2 = get_subscription_by_user_and_type(session, db_user.id, "news", category="technology")
    assert found2 is not None
    assert found2.id == sub2.id

    # Тест с деталями, но без категории
    sub3 = create_subscription(session, db_user.id, "weather", details="London", frequency=12)
    found3 = get_subscription_by_user_and_type(session, db_user.id, "weather", "London")
    assert found3 is not None
    assert found3.id == sub3.id
    assert get_subscription_by_user_and_type(session, db_user.id, "weather", "London", "sunny") is None

    # Тест без деталей и без категории
    sub4 = create_subscription(session, db_user.id, "news_all", frequency=6)
    found4 = get_subscription_by_user_and_type(session, db_user.id, "news_all")
    assert found4 is not None
    assert found4.id == sub4.id
    assert found4.details is None
    assert found4.category is None

def test_get_subscription_by_user_and_type_not_exists(session: Session, db_user: User):
    create_subscription(session, db_user.id, "weather", details="Paris", frequency=3)
    assert get_subscription_by_user_and_type(session, db_user.id, "news_sports") is None
    assert get_subscription_by_user_and_type(session, db_user.id, "weather", "Berlin") is None

def test_get_subscription_by_user_and_type_inactive(session: Session, db_user: User):
    sub = Subscription(user_id=db_user.id, info_type="weather", frequency=1, details="Oslo", status="inactive")
    session.add(sub); session.commit()
    assert get_subscription_by_user_and_type(session, db_user.id, "weather", "Oslo") is None

def test_delete_subscription_success(session: Session, db_user: User):
    sub_to_delete = create_subscription(session, db_user.id, "events", frequency=1)
    result = delete_subscription(session, sub_to_delete.id)
    assert result is True
    deactivated_sub = session.get(Subscription, sub_to_delete.id)
    assert deactivated_sub is not None
    assert deactivated_sub.status == "inactive"

def test_delete_subscription_not_found(session: Session):
    assert delete_subscription(session, 99999) is False

def test_create_log_entry_with_user(session: Session, db_user: User):
    log_entry = create_log_entry(session, db_user.id, "/start", "details")
    assert log_entry is not None

def test_log_user_action_handles_exception(session: Session):
    with patch("app.database.crud.create_log_entry", side_effect=Exception("DB error")):
        with patch("app.database.crud.logger.error") as mock_logger:
            log_user_action(session, 123, "/command")
            mock_logger.assert_called_once()

def test_get_session_closes_on_exception():
    """Тест: контекстный менеджер get_session закрывает сессию даже при исключении."""
    from app.database.session import get_session, engine

    # Мокируем сам класс Session, чтобы отследить вызов close() на его экземпляре
    with patch("app.database.session.Session") as mock_session_class:
        mock_session_instance = mock_session_class.return_value
        with pytest.raises(ValueError, match="Test exception"):
            with get_session() as session:
                # Убедимся, что мы получили наш мок
                assert session == mock_session_instance
                # Имитируем ошибку внутри блока with
                raise ValueError("Test exception")

        # Проверяем, что сессия была создана с правильным движком
        mock_session_class.assert_called_once_with(engine)
        mock_session_instance.close.assert_called_once()