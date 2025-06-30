"""
Модуль, содержащий модели данных для работы с базой данных.
Использует SQLModel для определения моделей и их связей.
"""

from typing import Optional, TYPE_CHECKING, List
from datetime import datetime, timezone
from sqlmodel import Field, SQLModel, Relationship

if TYPE_CHECKING:
    pass


class User(SQLModel, table=True):
    # ... (код без изменений) ...
    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: int = Field(
        index=True, unique=True
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    subscriptions: List["Subscription"] = Relationship(back_populates="user")
    logs: List["Log"] = Relationship(back_populates="user")


class Subscription(SQLModel, table=True):
    """
    Модель подписки пользователя.
    Хранит информацию о конкретной подписке пользователя на определенный тип информации.
    Поддерживает два типа расписания: интервальное (frequency) и по расписанию (cron_expression).
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    info_type: str = Field(index=True)

    # Поля для расписания
    frequency: Optional[int] = Field(default=None)  # Для интервалов (раз в N часов)
    cron_expression: Optional[str] = Field(default=None)  # Для cron-расписаний

    # Поля для уточнения контента
    details: Optional[str] = Field(default=None, index=True)  # Город для погоды/событий
    category: Optional[str] = Field(default=None, index=True)  # Категория для новостей/событий

    # Системные поля
    status: str = Field(default="active", index=True)
    last_sent_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user: Optional["User"] = Relationship(back_populates="subscriptions")

class Log(SQLModel, table=True):
    # ... (код без изменений) ...
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    command: str = Field(index=True)
    details: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user: Optional["User"] = Relationship(back_populates="logs")