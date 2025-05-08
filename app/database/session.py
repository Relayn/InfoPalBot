from sqlmodel import create_engine, SQLModel, Session # Импортируем Session для управления сессиями
from app.config import settings # Импортируем настройки приложения
# Импортируем модели, чтобы SQLAlchemy знал о них и мог создать таблицы
from app.database.models import User, Subscription, Log

# Строка подключения к базе данных берется из настроек
# connect_args={"check_same_thread": False} нужен только для SQLite при асинхронном использовании,
# так как SQLite по умолчанию разрешает доступ только из того же потока, который установил соединение.
# Для PostgreSQL или других БД этот аргумент не нужен.
engine = create_engine(settings.DATABASE_URL, echo=True, connect_args={"check_same_thread": False})

def create_db_and_tables():
    """
    Создает все таблицы в базе данных на основе моделей SQLModel.
    Вызывается при первом запуске или инициализации приложения.
    """
    print("Создание базы данных и таблиц...")
    SQLModel.metadata.create_all(engine)
    print("База данных и таблицы созданы.")

def get_session():
    """
    Генератор зависимостей для получения сессии базы данных.
    Используется для внедрения зависимости (Dependency Injection) в FastAPI
    или для ручного управления сессией.
    Сессия автоматически закрывается после использования.
    """
    with Session(engine) as session:
        yield session
