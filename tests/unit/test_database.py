import pytest
from sqlmodel import create_engine, Session, SQLModel, select
from sqlalchemy.exc import IntegrityError # Для проверки внешних ключей
from typing import List, Optional # Для типизации в тестах
from datetime import datetime, timezone, timedelta # Для updated_at

from app.database.models import User, Subscription, Log # Убедимся, что Subscription импортирована
from app.database.crud import (
    get_user_by_telegram_id,
    create_user,
    create_user_if_not_exists,
    create_subscription, # Добавляем импорты для Subscription CRUD
    get_subscriptions_by_user_id,
    get_subscription_by_user_and_type,
    delete_subscription
)

# Фикстура для создания временного движка базы данных SQLite in-memory
@pytest.fixture(name="engine")
def engine_fixture():
    """
    Фикстура Pytest для создания движка базы данных SQLite in-memory для тестирования.
    Таблицы создаются перед тестом и удаляются после него.
    """
    # Используем in-memory SQLite базу данных для тестов
    # connect_args={"check_same_thread": False} нужен для SQLite в многопоточной среде, как в тестах
    engine = create_engine("sqlite:///:memory:", echo=False, connect_args={"check_same_thread": False})

    # Создаем все таблицы перед выполнением теста
    SQLModel.metadata.create_all(engine)

    # 'yield' позволяет использовать движок в тесте
    yield engine

    # Код после 'yield' выполняется после завершения теста
    # Удаляем все таблицы
    SQLModel.metadata.drop_all(engine)


# Фикстура для получения тестовой сессии базы данных
@pytest.fixture(name="session")
def session_fixture(engine):
    """
    Фикстура Pytest для получения сессии базы данных из тестового движка.
    Сессия автоматически закрывается после выполнения теста.
    """
    # Используем контекстный менеджер для автоматического закрытия сессии
    with Session(engine) as session:
        # 'yield' предоставляет сессию тесту
        yield session


# --- Тесты для User CRUD ---

def test_get_user_by_existing_telegram_id(session: Session):
    """Тест: успешное получение пользователя по существующему Telegram ID."""
    telegram_id = 12345
    user_to_create = User(telegram_id=telegram_id)
    session.add(user_to_create)
    session.commit()
    session.refresh(user_to_create)

    found_user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)

    assert found_user is not None
    assert found_user.telegram_id == telegram_id
    assert found_user.id == user_to_create.id


def test_get_user_by_non_existing_telegram_id(session: Session):
    """Тест: получение пользователя по несуществующему Telegram ID должно вернуть None."""
    non_existing_telegram_id = 99999
    found_user = get_user_by_telegram_id(session=session, telegram_id=non_existing_telegram_id)
    assert found_user is None


def test_create_user_successfully(session: Session):
    """Тест: успешное создание нового пользователя."""
    telegram_id = 54321
    created_user = create_user(session=session, telegram_id=telegram_id)

    assert created_user is not None
    assert created_user.telegram_id == telegram_id
    assert created_user.id is not None
    retrieved_user = session.get(User, created_user.id)
    assert retrieved_user is not None
    assert retrieved_user.telegram_id == telegram_id


def test_create_user_with_existing_telegram_id_fails(session: Session):
    """Тест: попытка создать пользователя с уже существующим Telegram ID должна вызвать ошибку."""
    telegram_id = 112233
    user_to_create = User(telegram_id=telegram_id)
    session.add(user_to_create)
    session.commit()
    session.refresh(user_to_create)

    with pytest.raises(IntegrityError):
        create_user(session=session, telegram_id=telegram_id)
        # session.commit() # В нашей функции create_user commit уже есть


def test_create_user_if_not_exists_creates_new(session: Session):
    """Тест: create_user_if_not_exists должен создать нового пользователя, если его нет."""
    telegram_id = 67890
    initial_user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)
    assert initial_user is None

    user = create_user_if_not_exists(session=session, telegram_id=telegram_id)

    assert user is not None
    assert user.telegram_id == telegram_id
    assert user.id is not None
    found_user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)
    assert found_user is not None
    assert found_user.id == user.id


def test_create_user_if_not_exists_returns_existing(session: Session):
    """Тест: create_user_if_not_exists должен вернуть существующего пользователя, если он есть."""
    telegram_id = 98765
    user_to_create = User(telegram_id=telegram_id)
    session.add(user_to_create)
    session.commit()
    session.refresh(user_to_create)
    existing_user_id = user_to_create.id

    user = create_user_if_not_exists(session=session, telegram_id=telegram_id)

    assert user is not None
    assert user.telegram_id == telegram_id
    assert user.id == existing_user_id
    statement = select(User).where(User.telegram_id == telegram_id)
    all_users = session.exec(statement).all()
    assert len(all_users) == 1
    assert all_users[0].id == existing_user_id


# --- Тесты для Subscription CRUD ---

@pytest.fixture
def db_user(session: Session) -> User:
    """Фикстура для создания тестового пользователя."""
    user = create_user(session=session, telegram_id=111222) # Используем уникальный ID
    return user

def test_create_subscription_success(session: Session, db_user: User):
    """Тест: успешное создание новой подписки."""
    info_type = "weather"
    frequency = "daily"
    details = "Moscow"

    subscription = create_subscription(
        session=session,
        user_id=db_user.id,
        info_type=info_type,
        frequency=frequency,
        details=details
    )

    assert subscription is not None
    assert subscription.id is not None
    assert subscription.user_id == db_user.id
    assert subscription.info_type == info_type
    assert subscription.frequency == frequency
    assert subscription.details == details
    assert subscription.status == "active"
    assert subscription.user == db_user # Проверяем связь

    retrieved_sub = session.get(Subscription, subscription.id)
    assert retrieved_sub is not None
    assert retrieved_sub.info_type == info_type


def test_create_subscription_invalid_user_id_fails(session: Session):
    """Тест: попытка создать подписку с несуществующим user_id."""
    with pytest.raises(IntegrityError):
        create_subscription(
            session=session,
            user_id=99999, # Несуществующий user_id
            info_type="news",
            frequency="hourly"
        )
        # session.commit() # Наша функция create_subscription уже делает commit


def test_get_subscriptions_by_user_id(session: Session, db_user: User):
    """Тест: получение всех активных подписок пользователя."""
    sub1 = create_subscription(session, db_user.id, "news", "daily")
    sub2 = create_subscription(session, db_user.id, "weather", "hourly", "Kyiv")
    inactive_sub = Subscription(user_id=db_user.id, info_type="events", frequency="weekly", status="inactive")
    session.add(inactive_sub)
    session.commit() # Коммитим неактивную подписку

    subscriptions: List[Subscription] = get_subscriptions_by_user_id(session, db_user.id)

    assert len(subscriptions) == 2
    # Проверяем по ID, т.к. объекты могут быть разными экземплярами после извлечения из БД
    sub_ids_retrieved = {sub.id for sub in subscriptions}
    assert sub1.id in sub_ids_retrieved
    assert sub2.id in sub_ids_retrieved
    assert inactive_sub.id not in sub_ids_retrieved
    for sub in subscriptions:
        assert sub.status == "active"


def test_get_subscriptions_by_user_id_no_subscriptions(session: Session, db_user: User):
    """Тест: получение подписок для пользователя без подписок."""
    subscriptions = get_subscriptions_by_user_id(session, db_user.id)
    assert len(subscriptions) == 0


def test_get_subscription_by_user_and_type_exists(session: Session, db_user: User):
    """Тест: получение существующей подписки по типу и деталям."""
    info_type = "weather"
    details = "London"
    created_sub = create_subscription(session, db_user.id, info_type, "daily", details)

    found_sub = get_subscription_by_user_and_type(session, db_user.id, info_type, details)
    assert found_sub is not None
    assert found_sub.id == created_sub.id

    info_type_no_details = "news_general"
    created_sub_no_details = create_subscription(session, db_user.id, info_type_no_details, "weekly") # details=None
    found_sub_no_details = get_subscription_by_user_and_type(session, db_user.id, info_type_no_details, None)
    assert found_sub_no_details is not None
    assert found_sub_no_details.id == created_sub_no_details.id
    assert found_sub_no_details.details is None


def test_get_subscription_by_user_and_type_not_exists(session: Session, db_user: User):
    """Тест: получение несуществующей подписки по типу и деталям."""
    create_subscription(session, db_user.id, "weather", "daily", "Paris")

    found_sub = get_subscription_by_user_and_type(session, db_user.id, "news_sports")
    assert found_sub is None

    found_sub_diff_details = get_subscription_by_user_and_type(session, db_user.id, "weather", "Berlin")
    assert found_sub_diff_details is None


def test_get_subscription_by_user_and_type_inactive(session: Session, db_user: User):
    """Тест: get_subscription_by_user_and_type не должен возвращать неактивные подписки."""
    info_type = "weather"
    details = "Oslo"
    # Создаем подписку напрямую с нужным статусом
    sub = Subscription(user_id=db_user.id, info_type=info_type, frequency="daily", details=details, status="inactive")
    session.add(sub)
    session.commit()

    found_sub = get_subscription_by_user_and_type(session, db_user.id, info_type, details)
    assert found_sub is None


def test_delete_subscription_success(session: Session, db_user: User):
    """Тест: успешная 'деактивация' подписки."""
    subscription_to_deactivate = create_subscription(session, db_user.id, "events", "monthly")
    # Запоминаем время перед обновлением
    time_before_update = subscription_to_deactivate.updated_at

    subscription_id = subscription_to_deactivate.id
    result = delete_subscription(session, subscription_id)

    assert result is True
    deactivated_sub = session.get(Subscription, subscription_id)
    assert deactivated_sub is not None
    assert deactivated_sub.status == "inactive"
    # Проверяем, что updated_at действительно изменилось
    assert deactivated_sub.updated_at > time_before_update


def test_delete_subscription_not_found(session: Session):
    """Тест: попытка удалить несуществующую подписку."""
    result = delete_subscription(session, 99999) # Несуществующий ID
    assert result is False