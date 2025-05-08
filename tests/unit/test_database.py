import pytest
# Добавляем import select
from sqlmodel import create_engine, Session, SQLModel, select # <-- Добавили select сюда
from app.database.models import User, Subscription, Log # Импортируем все модели, чтобы создать их
from app.database.crud import get_user_by_telegram_id, create_user, create_user_if_not_exists

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


# --- Тесты для get_user_by_telegram_id ---

def test_get_user_by_existing_telegram_id(session: Session):
    """Тест: успешное получение пользователя по существующему Telegram ID."""
    # Создаем пользователя напрямую для теста
    telegram_id = 12345
    user_to_create = User(telegram_id=telegram_id)
    session.add(user_to_create)
    session.commit()
    session.refresh(user_to_create)

    # Вызываем тестируемую функцию
    found_user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)

    # Проверяем результат
    assert found_user is not None
    assert found_user.telegram_id == telegram_id
    assert found_user.id == user_to_create.id


def test_get_user_by_non_existing_telegram_id(session: Session):
    """Тест: получение пользователя по несуществующему Telegram ID должно вернуть None."""
    # Вызываем тестируемую функцию для несуществующего ID
    non_existing_telegram_id = 99999
    found_user = get_user_by_telegram_id(session=session, telegram_id=non_existing_telegram_id)

    # Проверяем результат
    assert found_user is None


# --- Тесты для create_user ---

def test_create_user_successfully(session: Session):
    """Тест: успешное создание нового пользователя."""
    telegram_id = 54321

    # Вызываем тестируемую функцию
    created_user = create_user(session=session, telegram_id=telegram_id)

    # Проверяем, что пользователь создан и корректно сохранен
    assert created_user is not None
    assert created_user.telegram_id == telegram_id
    assert created_user.id is not None # Должен быть присвоен ID базой данных
    # Проверяем, что пользователь действительно есть в базе
    retrieved_user = session.get(User, created_user.id)
    assert retrieved_user is not None
    assert retrieved_user.telegram_id == telegram_id


def test_create_user_with_existing_telegram_id_fails(session: Session):
    """Тест: попытка создать пользователя с уже существующим Telegram ID должна вызвать ошибку."""
    telegram_id = 112233
    # Сначала создаем пользователя
    user_to_create = User(telegram_id=telegram_id)
    session.add(user_to_create)
    session.commit()
    session.refresh(user_to_create)

    # Пытаемся создать пользователя с тем же ID еще раз
    # Ожидаем, что это вызовет ошибку из-за уникального ограничения (IntegrityError)
    # Используем более специфичное исключение IntegrityError из SQLAlchemy
    from sqlalchemy.exc import IntegrityError # Импортируем IntegrityError
    with pytest.raises(IntegrityError):
        create_user(session=session, telegram_id=telegram_id)

    # Опционально: проверить, что текст ошибки содержит информацию об уникальном ограничении
    # assert "UNIQUE constraint failed" in str(excinfo.value) # Пример для SQLite


# --- Тесты для create_user_if_not_exists ---

def test_create_user_if_not_exists_creates_new(session: Session):
    """Тест: create_user_if_not_exists должен создать нового пользователя, если его нет."""
    telegram_id = 67890

    # Проверяем, что пользователя нет изначально
    initial_user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)
    assert initial_user is None

    # Вызываем тестируемую функцию
    user = create_user_if_not_exists(session=session, telegram_id=telegram_id)

    # Проверяем, что пользователь был создан
    assert user is not None
    assert user.telegram_id == telegram_id
    assert user.id is not None

    # Проверяем, что пользователь теперь существует в базе
    found_user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)
    assert found_user is not None
    assert found_user.id == user.id


def test_create_user_if_not_exists_returns_existing(session: Session):
    """Тест: create_user_if_not_exists должен вернуть существующего пользователя, если он есть."""
    telegram_id = 98765
    # Создаем пользователя заранее
    user_to_create = User(telegram_id=telegram_id)
    session.add(user_to_create)
    session.commit()
    session.refresh(user_to_create)
    existing_user_id = user_to_create.id

    # Вызываем тестируемую функцию
    user = create_user_if_not_exists(session=session, telegram_id=telegram_id)

    # Проверяем, что вернулся именно существующий пользователь
    assert user is not None
    assert user.telegram_id == telegram_id
    assert user.id == existing_user_id

    # Проверяем, что в базе не появилось дубликатов
    statement = select(User).where(User.telegram_id == telegram_id) # Тут использовался select
    all_users = session.exec(statement).all()
    assert len(all_users) == 1
    assert all_users[0].id == existing_user_id