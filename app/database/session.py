from sqlalchemy import event # Добавляем event
from sqlalchemy.engine import Engine # Добавляем Engine для типизации
from sqlmodel import create_engine, SQLModel, Session
from app.config import settings
from app.database.models import User, Subscription, Log

# Этот слушатель будет выполняться при каждом новом соединении для SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Включает поддержку внешних ключей для SQLite."""
    # Проверяем, что это SQLite, чтобы не применять PRAGMA к другим БД
    if dbapi_connection.__class__.__module__ == "sqlite3":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Строка подключения к базе данных берется из настроек
engine = create_engine(settings.DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
# echo=True для отладки SQL запросов, echo=False для тестов и продакшена

def create_db_and_tables():
    """
    Создает все таблицы в базе данных на основе моделей SQLModel.
    Вызывается при первом запуске или инициализации приложения.
    """
    print("Создание базы данных и таблиц (если их нет)...")
    SQLModel.metadata.create_all(engine)
    print("База данных и таблицы проверены/созданы.")

def get_session():
    """
    Генератор зависимостей для получения сессии базы данных.
    """
    with Session(engine) as session:
        yield session

# if __name__ == "__main__":
#     create_db_and_tables()