"""
Модуль для выполнения операций CRUD (Create, Read, Update, Delete)
с моделями базы данных (User, Subscription, Log).
"""
import logging
from sqlmodel import Session, select
from typing import Optional, List
from datetime import datetime, timezone

from app.database.models import User, Subscription, Log

logger = logging.getLogger(__name__)


def get_user_by_telegram_id(session: Session, telegram_id: int) -> Optional[User]:
    """
    Находит пользователя в базе данных по его Telegram ID.

    Args:
        session (Session): Сессия базы данных.
        telegram_id (int): Уникальный идентификатор пользователя в Telegram.

    Returns:
        Optional[User]: Объект пользователя, если найден, иначе None.
    """
    statement = select(User).where(User.telegram_id == telegram_id)
    return session.exec(statement).first()


def create_user(session: Session, telegram_id: int) -> User:
    """
    Создает нового пользователя в базе данных.

    Args:
        session (Session): Сессия базы данных.
        telegram_id (int): Уникальный идентификатор пользователя в Telegram.

    Returns:
        User: Созданный объект пользователя.
    """
    db_user = User(telegram_id=telegram_id)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    logger.info(f"Пользователь создан: {db_user}")
    return db_user


def create_user_if_not_exists(session: Session, telegram_id: int) -> User:
    """
    Возвращает существующего пользователя или создает нового, если он не найден.

    Args:
        session (Session): Сессия базы данных.
        telegram_id (int): Уникальный идентификатор пользователя в Telegram.

    Returns:
        User: Существующий или только что созданный объект пользователя.
    """
    user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)
    if user is None:
        user = create_user(session=session, telegram_id=telegram_id)
    return user


def create_subscription(
    session: Session,
    user_id: int,
    info_type: str,
    details: Optional[str] = None,
    category: Optional[str] = None,
    frequency: Optional[int] = None,
    cron_expression: Optional[str] = None,
) -> Subscription:
    """
    Создает новую подписку для пользователя.

    Принимает либо frequency (для интервалов), либо cron_expression (для cron-задач).
    Выбрасывает ValueError, если не указан ни один из них или указаны оба.

    Args:
        session (Session): Сессия базы данных.
        user_id (int): ID пользователя, которому принадлежит подписка.
        info_type (str): Тип информации ('weather', 'news', 'events').
        details (Optional[str]): Дополнительная информация (например, город).
        category (Optional[str]): Категория для новостей или событий.
        frequency (Optional[int]): Частота отправки в часах.
        cron_expression (Optional[str]): Выражение CRON для расписания.

    Returns:
        Subscription: Созданный объект подписки.

    Raises:
        ValueError: Если параметры `frequency` и `cron_expression` заданы некорректно.
    """
    if frequency is None and cron_expression is None:
        raise ValueError("Должен быть указан либо frequency, либо cron_expression.")
    if frequency is not None and cron_expression is not None:
        raise ValueError("Нельзя указывать frequency и cron_expression одновременно.")

    db_subscription = Subscription(
        user_id=user_id,
        info_type=info_type,
        details=details,
        category=category,
        frequency=frequency,
        cron_expression=cron_expression,
        status="active",
    )
    session.add(db_subscription)
    session.commit()
    session.refresh(db_subscription)
    logger.info(f"Создана подписка: {db_subscription}")
    return db_subscription


def get_subscriptions_by_user_id(session: Session, user_id: int) -> List[Subscription]:
    """
    Получает список всех активных подписок для указанного пользователя.

    Args:
        session (Session): Сессия базы данных.
        user_id (int): ID пользователя.

    Returns:
        List[Subscription]: Список активных подписок.
    """
    statement = select(Subscription).where(
        Subscription.user_id == user_id, Subscription.status == "active"
    )
    return session.exec(statement).all()


def get_subscription_by_user_and_type(
    session: Session,
    user_id: int,
    info_type: str,
    details: Optional[str] = None,
    category: Optional[str] = None,
) -> Optional[Subscription]:
    """
    Находит активную подписку по набору критериев для проверки на дубликаты.

    Args:
        session (Session): Сессия базы данных.
        user_id (int): ID пользователя.
        info_type (str): Тип информации.
        details (Optional[str]): Детали (город).
        category (Optional[str]): Категория.

    Returns:
        Optional[Subscription]: Найденная подписка или None.
    """
    statement = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.info_type == info_type,
        Subscription.status == "active",
    )
    if details is not None:
        statement = statement.where(Subscription.details == details)
    else:
        statement = statement.where(Subscription.details.is_(None))

    if category is not None:
        statement = statement.where(Subscription.category == category)
    else:
        statement = statement.where(Subscription.category.is_(None))

    return session.exec(statement).first()


def delete_subscription(session: Session, subscription_id: int) -> bool:
    """
    Деактивирует подписку, устанавливая ее статус в 'inactive'.

    Args:
        session (Session): Сессия базы данных.
        subscription_id (int): ID подписки, которую нужно деактивировать.

    Returns:
        bool: True, если подписка найдена и деактивирована, иначе False.
    """
    subscription = session.get(Subscription, subscription_id)
    if not subscription:
        return False
    subscription.status = "inactive"
    subscription.updated_at = datetime.now(timezone.utc)
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    logger.info(f"Подписка ID {subscription_id} деактивирована.")
    return True


def create_log_entry(
    session: Session,
    user_id: Optional[int],
    command: str,
    details: Optional[str] = None,
) -> Log:
    """
    Создает запись в логе действий пользователя.

    Args:
        session (Session): Сессия базы данных.
        user_id (Optional[int]): ID пользователя, если он известен.
        command (str): Выполненная команда или действие.
        details (Optional[str]): Дополнительные детали действия.

    Returns:
        Log: Созданный объект лога.
    """
    db_log = Log(user_id=user_id, command=command, details=details)
    session.add(db_log)
    session.commit()
    session.refresh(db_log)
    return db_log


def log_user_action(
    db_session: Session, telegram_id: int, command: str, details: Optional[str] = None
):
    """
    Удобная обертка для логирования действия пользователя по его Telegram ID.

    Находит ID пользователя в БД и создает запись в логе.
    Безопасно обрабатывает случаи, когда пользователь не найден.

    Args:
        db_session (Session): Сессия базы данных.
        telegram_id (int): Telegram ID пользователя.
        command (str): Выполненная команда или действие.
        details (Optional[str]): Дополнительные детали.
    """
    user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
    user_db_id: Optional[int] = user.id if user else None
    try:
        create_log_entry(
            session=db_session, user_id=user_db_id, command=command, details=details
        )
    except Exception as e:
        logger.error(
            f"Не удалось создать запись в логе для пользователя {telegram_id}, команда {command}: {e}",
            exc_info=True,
        )