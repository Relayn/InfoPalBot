"""Модуль для управления сессиями и подключением к базе данных.

Этот модуль отвечает за создание движка (engine) SQLAlchemy, который является
центральной точкой доступа к базе данных. Он также предоставляет удобный
контекстный менеджер `get_session` для получения сессий SQLAlchemy,
гарантируя их правильное открытие и закрытие.

Ключевые компоненты:
- `engine`: Глобальный объект движка SQLAlchemy.
- `get_session()`: Контекстный менеджер для получения сессий БД.
- `set_sqlite_pragma()`: Слушатель событий для включения поддержки
  внешних ключей в SQLite, что критически важно для целостности данных.
"""
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.config import settings

# Слушатель событий SQLAlchemy, который выполняется при каждом новом соединении с БД.
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Включает поддержку внешних ключей (FOREIGN KEY) для SQLite.

    Эта функция автоматически вызывается SQLAlchemy при установке нового
    соединения с базой данных SQLite. Она выполняет команду PRAGMA,
    которая необходима для активации ограничений внешних ключей,
    обеспечивая целостность данных на уровне БД.

    Args:
        dbapi_connection: Объект соединения с базой данных (DBAPI).
        connection_record: Запись о соединении (не используется).
    """
    # Проверяем, что это соединение SQLite, чтобы не применять PRAGMA к другим БД
    if dbapi_connection.__class__.__module__ == "sqlite3":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


engine = create_engine(
    settings.DATABASE_URL, echo=False, connect_args={"check_same_thread": False}
)


@contextmanager
def get_session():
    """Предоставляет сессию базы данных через контекстный менеджер.

    Этот генератор создает новую сессию SQLAlchemy, предоставляет ее для
    использования внутри блока `with` и гарантированно закрывает ее
    по завершении блока, даже если внутри произошло исключение.

    Yields:
        Session: Экземпляр сессии базы данных для выполнения операций.
    """
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()