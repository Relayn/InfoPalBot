from sqlmodel import Session, select
from typing import Optional, List
from datetime import datetime, timezone # Убедимся, что timezone импортирован

from app.database.models import User, Subscription, Log # Импортируем Log

# --- CRUD для User (существующий код) ---
def get_user_by_telegram_id(session: Session, telegram_id: int) -> Optional[User]:
    # ... (существующий код)
    statement = select(User).where(User.telegram_id == telegram_id)
    user = session.exec(statement).first()
    return user

def create_user(session: Session, telegram_id: int) -> User:
    # ... (существующий код)
    db_user = User(telegram_id=telegram_id)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

def create_user_if_not_exists(session: Session, telegram_id: int) -> User:
    # ... (существующий код)
    user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)
    if user is None:
        print(f"Пользователь с telegram_id {telegram_id} не найден. Создаем нового.")
        user = create_user(session=session, telegram_id=telegram_id)
        print(f"Пользователь создан: {user}")
    else:
        print(f"Пользователь с telegram_id {telegram_id} найден: {user}")
    return user

# --- CRUD для Subscription ---

def create_subscription(session: Session,
                        user_id: int,
                        info_type: str,
                        frequency: str,
                        details: Optional[str] = None) -> Subscription:
    """
    Создает новую подписку для пользователя.

    Args:
        session (Session): Сессия базы данных SQLModel.
        user_id (int): ID пользователя (из таблицы User).
        info_type (str): Тип информации (например, "weather", "news_tech").
        frequency (str): Частота уведомлений (например, "daily", "hourly").
        details (Optional[str]): Дополнительные детали (например, город для погоды).

    Returns:
        Subscription: Созданный объект подписки.
    """
    db_subscription = Subscription(
        user_id=user_id,
        info_type=info_type,
        frequency=frequency,
        details=details,
        status="active" # По умолчанию подписка активна
    )
    session.add(db_subscription)
    session.commit()
    session.refresh(db_subscription)
    print(f"Создана подписка: {db_subscription}")
    return db_subscription

def get_subscriptions_by_user_id(session: Session, user_id: int) -> List[Subscription]:
    """
    Получает все активные подписки для указанного пользователя.

    Args:
        session (Session): Сессия базы данных SQLModel.
        user_id (int): ID пользователя.

    Returns:
        List[Subscription]: Список подписок пользователя.
    """
    statement = select(Subscription).where(Subscription.user_id == user_id).where(Subscription.status == "active")
    subscriptions = session.exec(statement).all()
    return subscriptions

def get_subscription_by_user_and_type(session: Session,
                                      user_id: int,
                                      info_type: str,
                                      details: Optional[str] = None) -> Optional[Subscription]:
    """
    Получает конкретную активную подписку пользователя по типу и деталям.
    Это поможет избежать дублирования подписок.

    Args:
        session (Session): Сессия базы данных SQLModel.
        user_id (int): ID пользователя.
        info_type (str): Тип информации.
        details (Optional[str]): Детали подписки (важно для уникальности, например, город).

    Returns:
        Optional[Subscription]: Найденная подписка или None.
    """
    statement = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.info_type == info_type,
        Subscription.status == "active" # Ищем только активные
    )
    # Если details предоставлены, добавляем их в условие
    # Для простоты пока сравниваем details как строку.
    # В более сложных случаях может потребоваться сравнение JSON-подобных структур.
    if details is not None:
        statement = statement.where(Subscription.details == details)
    else: # Если details не указаны, ищем подписку, где details тоже None
        statement = statement.where(Subscription.details.is_(None))

    subscription = session.exec(statement).first()
    return subscription


def delete_subscription(session: Session, subscription_id: int) -> bool:
    """
    Удаляет (или деактивирует) подписку по ее ID.
    Вместо фактического удаления можно менять статус на "inactive".

    Args:
        session (Session): Сессия базы данных SQLModel.
        subscription_id (int): ID подписки.

    Returns:
        bool: True, если подписка найдена и деактивирована/удалена, иначе False.
    """
    subscription = session.get(Subscription, subscription_id)
    if not subscription:
        return False

    # Вместо удаления, меняем статус на "inactive"
    subscription.status = "inactive"
    # Обновляем время изменения
    from datetime import datetime, timezone # Импортируем здесь, чтобы избежать циклического импорта, если crud.py импортируется в models.py
    subscription.updated_at = datetime.now(timezone.utc)
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    print(f"Подписка ID {subscription_id} деактивирована.")
    return True


def get_active_subscriptions_by_info_type(session: Session, info_type: str) -> List[Subscription]:
    """
    Получает все активные подписки для указанного типа информации.

    Args:
        session (Session): Сессия базы данных SQLModel.
        info_type (str): Тип информации (например, "weather", "news").

    Returns:
        List[Subscription]: Список активных подписок данного типа.
    """
    statement = select(Subscription).where(
        Subscription.info_type == info_type,
        Subscription.status == "active"
    )
    subscriptions = session.exec(statement).all()
    return subscriptions

# def update_subscription_frequency(...):
#     pass

def create_log_entry(session: Session,
                       user_id: Optional[int], # Может быть None, если действие не от конкретного пользователя
                       command: str,
                       details: Optional[str] = None) -> Log:
    """
    Создает новую запись в логе действий.

    Args:
        session (Session): Сессия базы данных SQLModel.
        user_id (Optional[int]): ID пользователя (из таблицы User), если применимо.
        command (str): Выполненная команда или тип действия (например, "/start", "subscribe_weather").
        details (Optional[str]): Дополнительные детали действия (например, аргументы команды).

    Returns:
        Log: Созданный объект лога.
    """
    db_log = Log(
        user_id=user_id,
        command=command,
        details=details
        # timestamp устанавливается автоматически через default_factory в модели
    )
    session.add(db_log)
    session.commit()
    session.refresh(db_log)
    # Логирование самого лога в консоль может быть избыточным, но для отладки можно:
    # print(f"Запись в лог добавлена: {db_log}")
    return db_log