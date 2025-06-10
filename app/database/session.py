"""
Модуль для управления подключением к базе данных и сессиями SQLModel.
Отвечает за создание движка БД, создание таблиц и предоставление сессий.

Основные компоненты:
1. Настройка SQLite для поддержки внешних ключей
2. Создание и конфигурация движка базы данных
3. Функции для создания таблиц
4. Генератор сессий для работы с БД

Пример использования:
    # Создание таблиц при запуске приложения
    create_db_and_tables()

    # Использование сессии в FastAPI
    @app.get("/users")
    def get_users(db: Session = Depends(get_session)):
        return db.query(User).all()

    # Использование сессии вручную
    with get_session() as session:
        users = session.query(User).all()
"""

from contextlib import contextmanager
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import create_engine, SQLModel, Session  # Импортируем необходимые классы
from app.config import settings  # Импортируем настройки приложения

# Импортируем все модели, чтобы SQLModel.metadata.create_all() знал о них
# и мог создать соответствующие таблицы в базе данных.
from app.database.models import User, Subscription, Log


# Слушатель событий SQLAlchemy, который выполняется при каждом новом соединении с БД.
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Включает поддержку внешних ключей (FOREIGN KEYS) для SQLite соединений.

    Функция:
    1. Проверяет, что соединение является SQLite
    2. Включает поддержку внешних ключей через PRAGMA
    3. Закрывает курсор после выполнения

    Args:
        dbapi_connection: Объект соединения с базой данных
        connection_record: Запись о соединении (не используется)

    Note:
        - Функция вызывается автоматически при каждом новом соединении
        - Критично для обеспечения целостности данных в SQLite
        - Применяется только к SQLite соединениям
    """
    # Проверяем, что это соединение SQLite, чтобы не применять PRAGMA к другим типам БД
    if dbapi_connection.__class__.__module__ == "sqlite3":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Создаем движок базы данных.
# settings.DATABASE_URL берется из конфигурации приложения (например, из .env).
# echo=False: не выводить SQL-запросы в консоль (для production). Для отладки можно установить в True.
# connect_args={"check_same_thread": False}: необходим для SQLite при асинхронном использовании
# (например, с FastAPI или Aiogram), так как SQLite по умолчанию разрешает доступ только из того же потока,
# который установил соединение. Для других БД этот аргумент не нужен.
engine = create_engine(
    settings.DATABASE_URL, echo=False, connect_args={"check_same_thread": False}
)


def create_db_and_tables():
    """
    Создает все таблицы в базе данных на основе моделей SQLModel.

    Функция:
    1. Выводит информационное сообщение о начале процесса
    2. Создает все таблицы, определенные в моделях
    3. Выводит сообщение об успешном завершении

    Note:
        - Вызывается при первом запуске или инициализации приложения
        - Если таблицы уже существуют, они не пересоздаются
        - Использует метаданные из SQLModel для определения структуры таблиц
        - Важно импортировать все модели перед вызовом этой функции
    """
    print(
        "Создание базы данных и таблиц (если их нет)..."
    )  # Вывод в консоль для информации
    SQLModel.metadata.create_all(engine)  # Создает таблицы, если их нет
    print("База данных и таблицы проверены/созданы.")  # Вывод в консоль


@contextmanager
def get_session():
    """
    Генератор зависимостей для получения сессии базы данных.

    Функция:
    1. Создает новую сессию с использованием движка БД
    2. Предоставляет сессию через контекстный менеджер
    3. Автоматически закрывает сессию после использования

    Yields:
        Session: Экземпляр сессии базы данных.

    Note:
        - Используется для внедрения зависимости в FastAPI
        - Может использоваться для ручного управления сессией
        - Сессия автоматически закрывается после использования
        - Поддерживает транзакции и откат изменений при ошибках
    """
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
