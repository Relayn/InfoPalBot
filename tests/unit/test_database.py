import pytest
from sqlmodel import create_engine, Session, SQLModel, select
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
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
    create_log_entry
)

# Фикстуры engine и session
@pytest.fixture(name="engine")
def engine_fixture():
    from sqlalchemy import event # Импорт здесь, чтобы не было на уровне модуля, если не нужно везде
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if dbapi_connection.__class__.__module__ == "sqlite3":
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    engine_instance = create_engine("sqlite:///:memory:", echo=False, connect_args={"check_same_thread": False})
    # Убедимся, что все модели известны SQLAlchemy перед созданием таблиц
    # Это важно, если модели определены в app.database.models, а тесты в другом месте
    from app.database import models as db_models # noqa - импорт нужен для SQLModel.metadata
    SQLModel.metadata.create_all(engine_instance)
    yield engine_instance
    SQLModel.metadata.drop_all(engine_instance)

@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session_instance:
        yield session_instance

# Фикстура для тестового пользователя, используемая в нескольких тестах
@pytest.fixture
def db_user(session: Session) -> User:
    user = create_user(session=session, telegram_id=111222)
    return user

# --- Тесты для User CRUD ---
def test_get_user_by_existing_telegram_id(session: Session):
    telegram_id = 12345
    user_to_create = User(telegram_id=telegram_id)
    session.add(user_to_create)
    session.commit(); session.refresh(user_to_create)
    found_user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)
    assert found_user is not None
    assert found_user.telegram_id == telegram_id

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
    create_user(session=session, telegram_id=telegram_id) # Создаем первого
    with pytest.raises(IntegrityError): # Ожидаем ошибку IntegrityError от SQLAlchemy/DB
        create_user(session=session, telegram_id=telegram_id) # Пытаемся создать дубликат
        session.commit() # Ошибка возникнет при попытке коммита

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

# --- Тесты для Subscription CRUD ---
def test_create_subscription_success(session: Session, db_user: User):
    info_type = "weather"; frequency = "daily"; details = "Moscow"
    subscription = create_subscription(session, db_user.id, info_type, frequency, details)
    assert subscription is not None; assert subscription.user_id == db_user.id
    assert subscription.info_type == info_type; assert subscription.details == details

def test_create_subscription_invalid_user_id_fails(session: Session):
    with pytest.raises(IntegrityError):
        create_subscription(session, 99999, "news", "hourly")
        # session.commit() # Для SQLite с PRAGMA ON, ошибка возникнет уже при add/flush или при commit

def test_get_subscriptions_by_user_id(session: Session, db_user: User):
    sub1 = create_subscription(session, db_user.id, "news", "daily")
    sub2 = create_subscription(session, db_user.id, "weather", "hourly", "Kyiv")
    inactive_sub = Subscription(user_id=db_user.id, info_type="events", frequency="weekly", status="inactive")
    session.add(inactive_sub); session.commit()
    subscriptions = get_subscriptions_by_user_id(session, db_user.id)
    assert len(subscriptions) == 2; assert sub1 in subscriptions; assert sub2 in subscriptions

def test_get_subscriptions_by_user_id_no_subscriptions(session: Session, db_user: User):
    assert len(get_subscriptions_by_user_id(session, db_user.id)) == 0

def test_get_subscription_by_user_and_type_exists(session: Session, db_user: User):
    created_sub = create_subscription(session, db_user.id, "weather", "daily", "London")
    found_sub = get_subscription_by_user_and_type(session, db_user.id, "weather", "London")
    assert found_sub is not None; assert found_sub.id == created_sub.id
    created_sub_no_details = create_subscription(session, db_user.id, "news_general", "weekly")
    found_sub_no_details = get_subscription_by_user_and_type(session, db_user.id, "news_general")
    assert found_sub_no_details is not None; assert found_sub_no_details.details is None

def test_get_subscription_by_user_and_type_not_exists(session: Session, db_user: User):
    create_subscription(session, db_user.id, "weather", "daily", "Paris")
    assert get_subscription_by_user_and_type(session, db_user.id, "news_sports") is None
    assert get_subscription_by_user_and_type(session, db_user.id, "weather", "Berlin") is None

def test_get_subscription_by_user_and_type_inactive(session: Session, db_user: User):
    sub = Subscription(user_id=db_user.id, info_type="weather", frequency="daily", details="Oslo", status="inactive")
    session.add(sub); session.commit()
    assert get_subscription_by_user_and_type(session, db_user.id, "weather", "Oslo") is None

def test_delete_subscription_success(session: Session, db_user: User):
    initial_time_aware = datetime.now(timezone.utc) - timedelta(minutes=1)
    sub_to_delete = create_subscription(session, db_user.id, "events", "monthly")
    sub_to_delete.updated_at = initial_time_aware
    session.add(sub_to_delete)
    session.commit()
    session.refresh(sub_to_delete)
    aware_initial_time = sub_to_delete.updated_at
    result = delete_subscription(session, sub_to_delete.id)
    assert result is True
    deactivated_sub = session.get(Subscription, sub_to_delete.id)
    assert deactivated_sub is not None
    assert deactivated_sub.status == "inactive"
    # Приводим deactivated_sub.updated_at (из БД, вероятно naive) к aware UTC
    updated_at_from_db_naive = deactivated_sub.updated_at
    updated_at_from_db_aware = updated_at_from_db_naive
    if updated_at_from_db_naive.tzinfo is None or updated_at_from_db_naive.tzinfo.utcoffset(
            updated_at_from_db_naive) is None:
        updated_at_from_db_aware = updated_at_from_db_naive.replace(tzinfo=timezone.utc)

    # Теперь оба значения aware и могут быть сравнены
    assert updated_at_from_db_aware > initial_time_aware

def test_delete_subscription_not_found(session: Session):
    assert delete_subscription(session, 99999) is False

# --- Тесты для Log CRUD ---

def test_create_log_entry_with_user(session: Session, db_user: User):
    command = "/start"; details = "User started the bot"
    log_entry = create_log_entry(session, db_user.id, command, details)
    assert log_entry is not None; assert log_entry.user_id == db_user.id
    assert log_entry.command == command; assert log_entry.details == details
    assert log_entry.timestamp is not None
    # Исправление для TypeError: can't subtract offset-naive and offset-aware datetimes
    timestamp_to_compare = log_entry.timestamp
    if timestamp_to_compare.tzinfo is None or timestamp_to_compare.tzinfo.utcoffset(timestamp_to_compare) is None:
        timestamp_to_compare = timestamp_to_compare.replace(tzinfo=timezone.utc)
    assert (datetime.now(timezone.utc) - timestamp_to_compare).total_seconds() < 5
    retrieved_log = session.get(Log, log_entry.id)
    assert retrieved_log is not None

def test_create_log_entry_without_user(session: Session):
    command = "system_event"; details = "Scheduler started"
    log_entry = create_log_entry(session, None, command, details)
    assert log_entry is not None; assert log_entry.user_id is None
    assert log_entry.command == command; assert log_entry.details == details

def test_create_log_entry_command_too_long_if_constrained(session: Session):
    command = "a" * 1000
    log_entry = create_log_entry(session, None, command)
    assert log_entry is not None; assert len(log_entry.command) == 1000

def test_create_log_entry_no_details(session: Session, db_user: User):
    command = "/help"
    log_entry = create_log_entry(session, db_user.id, command, details=None)
    assert log_entry is not None; assert log_entry.details is None