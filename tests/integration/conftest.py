import pytest
from sqlmodel import create_engine, Session, SQLModel
from sqlalchemy import event
from sqlalchemy.engine import Engine

@pytest.fixture(name="integration_engine")
def engine_fixture():
    """Создает движок БД SQLite в памяти для интеграционных тестов."""

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if dbapi_connection.__class__.__module__ == "sqlite3":
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    engine_instance = create_engine(
        "sqlite:///:memory:", echo=False, connect_args={"check_same_thread": False}
    )
    # Убедимся, что все модели известны SQLAlchemy перед созданием таблиц
    from app.database import models as db_models_import # noqa - импорт нужен для SQLModel.metadata
    SQLModel.metadata.create_all(engine_instance)
    yield engine_instance
    SQLModel.metadata.drop_all(engine_instance)


@pytest.fixture(name="integration_session")
def session_fixture(integration_engine: Engine):
    """Создает сессию БД для каждого теста."""
    with Session(integration_engine) as session_instance:
        yield session_instance