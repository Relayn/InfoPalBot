"""
Модуль, содержащий модели данных для работы с базой данных.
Использует SQLModel для определения моделей и их связей.
"""

from typing import Optional, TYPE_CHECKING, List
from datetime import datetime, timezone  # Используем timezone вместо pytz
from sqlmodel import Field, SQLModel, Relationship

# TYPE_CHECKING используется для аннотаций типов связей, чтобы избежать
# проблем с циклическими импортами, если модели будут разделены на разные файлы.
if TYPE_CHECKING:
    # Здесь можно было бы импортировать модели, если бы они были в разных файлах
    # from .user import User
    # from .subscription import Subscription
    pass  # В данном случае импорт не требуется, так как все модели в одном файле


class User(SQLModel, table=True):
    """
    Модель пользователя Telegram.
    Хранит основную информацию о пользователе, взаимодействующем с ботом.

    Attributes:
        id (Optional[int]): Первичный ключ, автоинкрементный ID в базе данных.
        telegram_id (int): Уникальный ID пользователя в Telegram. Индексируется для быстрого поиска.
        created_at (datetime): Время создания записи в UTC. Устанавливается автоматически.
        subscriptions (List[Subscription]): Связь с подписками пользователя (обратная связь).
        logs (List[Log]): Связь с логами действий пользователя (обратная связь).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: int = Field(
        index=True, unique=True
    )  # Уникальный ID пользователя в Telegram
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )  # Время создания записи в UTC

    # Отношения с другими моделями (обратные связи)
    subscriptions: List["Subscription"] = Relationship(back_populates="user")
    logs: List["Log"] = Relationship(back_populates="user")


class Subscription(SQLModel, table=True):
    """
    Модель подписки пользователя.
    Хранит информацию о конкретной подписке пользователя на определенный тип информации.

    Attributes:
        id (Optional[int]): Первичный ключ, автоинкрементный ID в базе данных.
        user_id (Optional[int]): Внешний ключ к таблице User. Индексируется для быстрого поиска.
        info_type (str): Тип информации (например, "weather", "news", "events"). Индексируется.
        frequency (str): Частота уведомлений (например, "daily", "hourly").
        details (Optional[str]): Дополнительные детали подписки (например, город для погоды/событий).
        status (str): Статус подписки ("active" или "inactive"). По умолчанию "active".
        created_at (datetime): Время создания подписки в UTC. Устанавливается автоматически.
        updated_at (datetime): Время последнего обновления подписки в UTC. Устанавливается автоматически.
        user (Optional[User]): Связь с пользователем (прямая связь).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    # Внешний ключ, ссылается на столбец 'id' в таблице 'user'.
    # Optional[int] и default=None, так как поле может быть None до сохранения или при создании.
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)

    info_type: str = Field(
        index=True
    )  # Тип информации (например, "weather", "news", "events")
    frequency: (
        str  # Частота уведомлений (например, "daily", "hourly"). Может быть Enum.
    )
    details: Optional[str] = (
        None  # Дополнительные детали подписки (например, город для погоды/событий, категория новостей)
    )
    status: str = (
        "active"  # Статус подписки (например, "active", "inactive"). Может быть Enum.
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )  # Время создания подписки в UTC
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )  # Время последнего обновления подписки в UTC

    # Отношение к модели User (прямая связь)
    user: Optional["User"] = Relationship(back_populates="subscriptions")


class Log(SQLModel, table=True):
    """
    Модель для логирования запросов и действий пользователей.
    Используется для отслеживания активности пользователей и отладки.

    Attributes:
        id (Optional[int]): Первичный ключ, автоинкрементный ID в базе данных.
        user_id (Optional[int]): Внешний ключ к таблице User. Может быть None для системных действий.
        command (str): Выполненная команда или тип действия. Индексируется для быстрого поиска.
        details (Optional[str]): Дополнительные детали действия (например, аргументы команды).
        timestamp (datetime): Время выполнения действия в UTC. Устанавливается автоматически.
        user (Optional[User]): Связь с пользователем (прямая связь).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    # Внешний ключ к таблице пользователей. Optional, т.к. действие может быть от незарегистрированного пользователя
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)

    command: str = Field(
        index=True
    )  # Выполненная команда или тип действия (например, "/start", "subscribe_weather", "api_error")
    details: Optional[str] = (
        None  # Дополнительные детали действия (например, аргументы команды, сообщение об ошибке)
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )  # Время выполнения действия в UTC

    # Отношение к модели User (прямая связь)
    user: Optional["User"] = Relationship(back_populates="logs")
