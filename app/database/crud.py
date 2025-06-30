# Файл: app/database/crud.py

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

# --- User CRUD (без изменений) ---
def get_user_by_telegram_id(session: Session, telegram_id: int) -> Optional[User]:
    statement = select(User).where(User.telegram_id == telegram_id)
    return session.exec(statement).first()

def create_user(session: Session, telegram_id: int) -> User:
    db_user = User(telegram_id=telegram_id)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    logger.info(f"Пользователь создан: {db_user}")
    return db_user

def create_user_if_not_exists(session: Session, telegram_id: int) -> User:
    user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)
    if user is None:
        user = create_user(session=session, telegram_id=telegram_id)
    return user

# --- Subscription CRUD (ИЗМЕНЕНО) ---

def create_subscription(
    session: Session,
    user_id: int,
    info_type: str,
    details: Optional[str] = None,
    frequency: Optional[int] = None,
    cron_expression: Optional[str] = None,
) -> Subscription:
    """
    Создает новую подписку для пользователя.
    Принимает либо frequency (для интервалов), либо cron_expression.
    """
    if frequency is None and cron_expression is None:
        raise ValueError("Должен быть указан либо frequency, либо cron_expression.")
    if frequency is not None and cron_expression is not None:
        raise ValueError("Нельзя указывать frequency и cron_expression одновременно.")

    db_subscription = Subscription(
        user_id=user_id,
        info_type=info_type,
        details=details,
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
    statement = select(Subscription).where(
        Subscription.user_id == user_id, Subscription.status == "active"
    )
    return session.exec(statement).all()

def get_subscription_by_user_and_type(
    session: Session, user_id: int, info_type: str, details: Optional[str] = None
) -> Optional[Subscription]:
    statement = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.info_type == info_type,
        Subscription.status == "active",
    )
    if details is not None:
        statement = statement.where(Subscription.details == details)
    else:
        statement = statement.where(Subscription.details.is_(None))
    return session.exec(statement).first()

def delete_subscription(session: Session, subscription_id: int) -> bool:
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

# --- Log CRUD (без изменений) ---
def create_log_entry(
    session: Session,
    user_id: Optional[int],
    command: str,
    details: Optional[str] = None,
) -> Log:
    db_log = Log(user_id=user_id, command=command, details=details)
    session.add(db_log)
    session.commit()
    session.refresh(db_log)
    return db_log

def log_user_action(
    db_session: Session, telegram_id: int, command: str, details: Optional[str] = None
):
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