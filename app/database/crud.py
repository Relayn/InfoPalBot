from sqlmodel import Session, select # Импортируем Session для работы с БД и select для построения запросов
from typing import Optional # Используем Optional для функций, которые могут вернуть None
from app.database.models import User # Импортируем модель User

def get_user_by_telegram_id(session: Session, telegram_id: int) -> Optional[User]:
    """
    Получает пользователя из базы данных по его Telegram ID.

    Args:
        session (Session): Сессия базы данных SQLModel.
        telegram_id (int): Уникальный идентификатор пользователя в Telegram.

    Returns:
        Optional[User]: Объект пользователя, если найден, иначе None.
    """
    # Строим SQL-запрос для выборки пользователя по telegram_id
    statement = select(User).where(User.telegram_id == telegram_id)
    # Выполняем запрос и получаем первый результат (или None, если ничего не найдено)
    user = session.exec(statement).first()
    return user

def create_user(session: Session, telegram_id: int) -> User:
    """
    Создает нового пользователя в базе данных.

    Args:
        session (Session): Сессия базы данных SQLModel.
        telegram_id (int): Уникальный идентификатор пользователя в Telegram.

    Returns:
        User: Созданный объект пользователя.
    """
    # Создаем новый экземпляр модели User
    db_user = User(telegram_id=telegram_id)
    # Добавляем объект в сессию
    session.add(db_user)
    # Фиксируем изменения в базе данных
    session.commit()
    # Обновляем объект, чтобы получить присвоенный ID из базы данных
    session.refresh(db_user)
    return db_user

def create_user_if_not_exists(session: Session, telegram_id: int) -> User:
    """
    Получает пользователя по Telegram ID. Если пользователь не найден, создает нового.

    Args:
        session (Session): Сессия базы данных SQLModel.
        telegram_id (int): Уникальный идентификатор пользователя в Telegram.

    Returns:
        User: Существующий или новый объект пользователя.
    """
    # Сначала пытаемся найти пользователя
    user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)
    # Если пользователь не найден, создаем нового
    if user is None:
        print(f"Пользователь с telegram_id {telegram_id} не найден. Создаем нового.")
        user = create_user(session=session, telegram_id=telegram_id)
        print(f"Пользователь создан: {user}")
    else:
        print(f"Пользователь с telegram_id {telegram_id} найден: {user}")
    return user

# Пока оставляем CRUD для других моделей и операций пустым
# def get_subscription(...):
#     pass
# def create_subscription(...):
#     pass
# def create_log_entry(...):
#     pass