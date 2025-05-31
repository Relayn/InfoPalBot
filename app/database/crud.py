"""
Модуль для выполнения операций CRUD (Create, Read, Update, Delete)
с моделями базы данных (User, Subscription, Log).

Этот модуль предоставляет функции для:
- Управления пользователями (создание, поиск)
- Управления подписками (создание, получение, деактивация)
- Логирования действий пользователей

Все функции работают с сессией SQLModel и возвращают типизированные объекты моделей.
"""

from sqlmodel import Session, select
from typing import Optional, List
from datetime import (
    datetime,
    timezone,
)  # Используем datetime.timezone для aware datetimes

from app.database.models import User, Subscription, Log


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
    # Печать в консоль для отладки, можно удалить в production
    print(f"Пользователь создан: {db_user}")
    return db_user


def create_user_if_not_exists(session: Session, telegram_id: int) -> User:
    """
    Получает пользователя по Telegram ID. Если пользователь не найден, создает нового.
    Эта функция является основным методом регистрации пользователей в системе.

    Args:
        session (Session): Сессия базы данных SQLModel.
        telegram_id (int): Уникальный идентификатор пользователя в Telegram.

    Returns:
        User: Существующий или новый объект пользователя.

    Note:
        Функция автоматически создает нового пользователя, если он не найден,
        что делает её удобной для использования при первом взаимодействии с ботом.
    """
    # Сначала пытаемся найти пользователя
    user = get_user_by_telegram_id(session=session, telegram_id=telegram_id)
    # Если пользователь не найден, создаем нового
    if user is None:
        # Печать в консоль для отладки, можно удалить в production
        print(f"Пользователь с telegram_id {telegram_id} не найден. Создаем нового.")
        user = create_user(session=session, telegram_id=telegram_id)
        # Печать в консоль для отладки, можно удалить в production
        print(f"Пользователь создан: {user}")
    else:
        # Печать в консоль для отладки, можно удалить в production
        print(f"Пользователь с telegram_id {telegram_id} найден: {user}")
    return user


def create_subscription(
    session: Session,
    user_id: int,
    info_type: str,
    frequency: str,
    details: Optional[str] = None,
) -> Subscription:
    """
    Создает новую подписку для пользователя.
    Эта функция используется как при ручной подписке через команды бота,
    так и при автоматическом создании подписок.

    Args:
        session (Session): Сессия базы данных SQLModel.
        user_id (int): ID пользователя (из таблицы User), к которому относится подписка.
        info_type (str): Тип информации (например, "weather", "news_tech").
        frequency (str): Частота уведомлений (например, "daily", "hourly").
        details (Optional[str]): Дополнительные детали (например, город для погоды).

    Returns:
        Subscription: Созданный объект подписки.

    Note:
        - Подписка создается со статусом "active"
        - Время создания и обновления устанавливается автоматически
        - Перед созданием новой подписки рекомендуется проверить
          наличие существующей через get_subscription_by_user_and_type
    """
    db_subscription = Subscription(
        user_id=user_id,
        info_type=info_type,
        frequency=frequency,
        details=details,
        status="active",  # По умолчанию подписка активна при создании
    )
    session.add(db_subscription)
    session.commit()
    session.refresh(db_subscription)
    # Печать в консоль для отладки, можно удалить в production
    print(f"Создана подписка: {db_subscription}")
    return db_subscription


def get_subscriptions_by_user_id(session: Session, user_id: int) -> List[Subscription]:
    """
    Получает все активные подписки для указанного пользователя.

    Args:
        session (Session): Сессия базы данных SQLModel.
        user_id (int): ID пользователя.

    Returns:
        List[Subscription]: Список активных подписок пользователя.
    """
    # Выбираем подписки по user_id, которые имеют статус "active"
    statement = select(Subscription).where(
        Subscription.user_id == user_id, Subscription.status == "active"
    )
    subscriptions = session.exec(statement).all()
    return subscriptions


def get_subscription_by_user_and_type(
    session: Session, user_id: int, info_type: str, details: Optional[str] = None
) -> Optional[Subscription]:
    """
    Получает конкретную активную подписку пользователя по типу информации и деталям.
    Используется для проверки на дубликаты.

    Args:
        session (Session): Сессия базы данных SQLModel.
        user_id (int): ID пользователя.
        info_type (str): Тип информации подписки.
        details (Optional[str]): Детали подписки (например, город).

    Returns:
        Optional[Subscription]: Найденная подписка или None.
    """
    # Строим запрос для поиска активной подписки по user_id, info_type и status
    statement = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.info_type == info_type,
        Subscription.status == "active",
    )
    # Добавляем условие для details: либо совпадает, либо оба None
    if details is not None:
        statement = statement.where(Subscription.details == details)
    else:
        statement = statement.where(Subscription.details.is_(None))

    subscription = session.exec(statement).first()
    return subscription


def delete_subscription(session: Session, subscription_id: int) -> bool:
    """
    Деактивирует (меняет статус на "inactive") подписку по ее ID.
    Фактическое удаление строк из БД не производится для сохранения истории.

    Args:
        session (Session): Сессия базы данных SQLModel.
        subscription_id (int): ID подписки, которую нужно деактивировать.

    Returns:
        bool: True, если подписка найдена и деактивирована, иначе False.
    """
    # Находим подписку по ID
    subscription = session.get(Subscription, subscription_id)
    if not subscription:
        return False

    # Меняем статус на "inactive" и обновляем время изменения
    subscription.status = "inactive"
    subscription.updated_at = datetime.now(timezone.utc)  # Обновляем время в UTC
    session.add(subscription)  # Добавляем измененный объект в сессию
    session.commit()  # Фиксируем изменения
    session.refresh(
        subscription
    )  # Обновляем объект из БД, чтобы убедиться в изменениях
    # Печать в консоль для отладки, можно удалить в production
    print(f"Подписка ID {subscription_id} деактивирована.")
    return True


def get_active_subscriptions_by_info_type(
    session: Session, info_type: str
) -> List[Subscription]:
    """
    Получает все активные подписки для указанного типа информации.
    Используется планировщиком для рассылок.

    Args:
        session (Session): Сессия базы данных SQLModel.
        info_type (str): Тип информации (например, "weather", "news").

    Returns:
        List[Subscription]: Список активных подписок данного типа.
    """
    # Выбираем подписки по типу информации, которые имеют статус "active"
    statement = select(Subscription).where(
        Subscription.info_type == info_type, Subscription.status == "active"
    )
    subscriptions = session.exec(statement).all()
    return subscriptions


def create_log_entry(
    session: Session,
    user_id: Optional[int],
    command: str,
    details: Optional[str] = None,
) -> Log:
    """
    Создает новую запись в логе действий.

    Args:
        session (Session): Сессия базы данных SQLModel.
        user_id (Optional[int]): ID пользователя (из таблицы User), если применимо.
                                 Может быть None для системных действий или незарегистрированных пользователей.
        command (str): Выполненная команда или тип действия
                       (например, "/start", "subscribe_weather", "api_error").
        details (Optional[str]): Дополнительные детали действия
                                 (например, аргументы команды, сообщение об ошибке, до 250 символов).

    Returns:
        Log: Созданный объект лога.
    """
    db_log = Log(
        user_id=user_id,
        command=command,
        details=details,
        # timestamp устанавливается автоматически через default_factory в модели Log
    )
    session.add(db_log)  # Добавляем объект в сессию
    session.commit()  # Фиксируем изменения
    session.refresh(
        db_log
    )  # Обновляем объект, чтобы получить присвоенный ID и актуальное время
    return db_log
