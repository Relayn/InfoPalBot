"""
Модуль для управления подключением к базе данных и сессиями SQLModel.
Отвечает за создание движка БД, создание таблиц и предоставление сессий.
"""

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import create_engine, SQLModel, Session # Импортируем необходимые классы
from app.config import settings # Импортируем настройки приложения

# Импортируем все модели, чтобы SQLModel.metadata.create_all() знал о них
# и мог создать соответствующие таблицы в базе данных.
from app.database.models import User, Subscription, Log


# Слушатель событий SQLAlchemy, который выполняется при каждом новом соединении с БД.
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Включает поддержку внешних ключей (FOREIGN KEYS) для SQLite соединений.
    Это критично для обеспечения целостности данных в SQLite, так как по умолчанию
    внешние ключи не проверяются.
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
engine = create_engine(settings.DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def create_db_and_tables():
    """
    Создает все таблицы в базе данных на основе моделей SQLModel.
    Вызывается при первом запуске или инициализации приложения.
    Если таблицы уже существуют, они не пересоздаются.
    """
    print("Создание базы данных и таблиц (если их нет)...") # Вывод в консоль для информации
    SQLModel.metadata.create_all(engine) # Создает таблицы, если их нет
    print("База данных и таблицы проверены/созданы.") # Вывод в консоль


def get_session():
    """
    Генератор зависимостей для получения сессии базы данных.
    Используется для внедрения зависимости (Dependency Injection) в FastAPI
    или для ручного управления сессией в других частях приложения.
    Сессия автоматически закрывается после использования благодаря 'with' контекстному менеджеру.

    Yields:
        Session: Экземпляр сессии базы данных.
    """
    with Session(engine) as session:
        yield session