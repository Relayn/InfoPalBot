"""Модуль, определяющий модели данных для базы данных.

Этот файл содержит классы, которые с помощью SQLModel сопоставляются
с таблицами в базе данных. Каждая модель представляет собой таблицу и определяет
ее столбцы, типы данных и связи между таблицами.

Модели:
- User: Представляет пользователя Telegram.
- Subscription: Представляет подписку пользователя на определенный тип
  информации.
- Log: Представляет запись в логе о действиях пользователя.
"""
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    # Этот блок используется для разрешения циклических зависимостей
    # при проверке типов, не вызывая реального импорта.
    pass


class User(SQLModel, table=True):
    """Модель пользователя, хранящаяся в базе данных.

    Attributes:
        id: Уникальный идентификатор записи в БД (первичный ключ).
        telegram_id: Уникальный идентификатор пользователя в Telegram.
        created_at: Дата и время создания записи о пользователе.
        subscriptions: Связь "один ко многим" со всеми подписками пользователя.
        logs: Связь "один ко многим" со всеми логами действий пользователя.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: int = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    subscriptions: List["Subscription"] = Relationship(back_populates="user")
    logs: List["Log"] = Relationship(back_populates="user")


class Subscription(SQLModel, table=True):
    """Модель подписки пользователя на информационную рассылку.

    Хранит информацию о конкретной подписке, включая тип информации,
    детали (например, город), расписание и статус.

    Attributes:
        id: Уникальный идентификатор подписки (первичный ключ).
        user_id: Внешний ключ, связывающий подписку с пользователем.
        info_type: Тип информации ('weather', 'news', 'events').
        frequency: Частота рассылки в часах (для интервальных задач).
        cron_expression: Выражение CRON для задач по расписанию.
        details: Уточняющие детали (например, город для погоды).
        category: Категория для новостей или событий.
        status: Статус подписки ('active' или 'inactive').
        last_sent_at: Дата и время последней успешной отправки.
        created_at: Дата и время создания подписки.
        updated_at: Дата и время последнего обновления подписки.
        user: Обратная связь "многие к одному" с моделью User.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    info_type: str = Field(index=True)

    # Поля для расписания
    frequency: Optional[int] = Field(default=None)
    cron_expression: Optional[str] = Field(default=None)

    # Поля для уточнения контента
    details: Optional[str] = Field(default=None, index=True)
    category: Optional[str] = Field(default=None, index=True)

    # Системные поля
    status: str = Field(default="active", index=True)
    last_sent_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user: Optional["User"] = Relationship(back_populates="subscriptions")


class Log(SQLModel, table=True):
    """Модель для логирования действий пользователя.

    Каждая запись представляет собой одно действие, выполненное пользователем,
    например, вызов команды.

    Attributes:
        id: Уникальный идентификатор записи лога (первичный ключ).
        user_id: Внешний ключ, связывающий лог с пользователем (если он есть).
        command: Выполненная команда или действие (например, '/start').
        details: Дополнительные детали действия.
        timestamp: Дата и время, когда произошло действие.
        user: Обратная связь "многие к одному" с моделью User.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    command: str = Field(index=True)
    details: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user: Optional["User"] = Relationship(back_populates="logs")