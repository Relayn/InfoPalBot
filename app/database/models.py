from typing import Optional, TYPE_CHECKING, List
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship # Импортируем Relationship для связей
import pytz # Импортируем pytz для работы с часовыми поясами

# TYPE_CHECKING используется для аннотаций типов связей, чтобы избежать циклических импортов
# Предполагаем, что все модели находятся в этом файле, но используем TYPE_CHECKING как хорошую практику
# для будущего возможного разделения на файлы.
if TYPE_CHECKING:
    # from .user import User # Если бы User была в отдельном файле
    # from .subscription import Subscription # Если бы Subscription была в отдельном файле
    pass # В данном случае импорт не требуется, так как все модели в одном файле

class User(SQLModel, table=True):
    """
    Модель пользователя Telegram.
    Хранит информацию о пользователе, взаимодействующем с ботом.

    Attributes:
        id (Optional[int]): Уникальный идентификатор пользователя в базе данных.
                           Автоматически генерируется (Primary Key).
        telegram_id (int): Уникальный идентификатор пользователя в Telegram.
                           Используется для связи с Telegram API.
        created_at (datetime): Дата и время регистрации пользователя в системе.
                               Хранится в формате UTC.
        subscriptions (List["Subscription"]): Список подписок пользователя.
                                             Устанавливается через Relationship.
        logs (List["Log"]): Список записей лога, связанных с этим пользователем.
                            Устанавливается через Relationship.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: int = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(pytz.utc))

    # Отношение к моделям Subscription и Log
    subscriptions: List["Subscription"] = Relationship(back_populates="user")
    logs: List["Log"] = Relationship(back_populates="user")


class Subscription(SQLModel, table=True):
    """
    Модель подписки пользователя.
    Хранит информацию о конкретной подписке пользователя на определенный тип информации.

    Attributes:
        id (Optional[int]): Уникальный идентификатор подписки в базе данных.
                           Автоматически генерируется (Primary Key).
        user_id (Optional[int]): Идентификатор пользователя, к которому относится подписка.
                                 Внешний ключ к таблице пользователей.
        info_type (str): Тип информации подписки (например, "weather", "news", "events").
        frequency (str): Частота уведомлений (например, "daily", "hourly", "weekly").
        details (Optional[str]): Дополнительные детали подписки (например, город для погоды, категория новостей).
        status (str): Статус подписки (например, "active", "inactive").
        created_at (datetime): Дата и время создания подписки.
        updated_at (datetime): Дата и время последнего обновления подписки.
        user (User): Пользователь, к которому относится эта подписка.
                     Устанавливается через Relationship.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)

    info_type: str = Field(index=True)
    frequency: str
    details: Optional[str] = None
    status: str = "active"

    created_at: datetime = Field(default_factory=lambda: datetime.now(pytz.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(pytz.utc))

    user: Optional["User"] = Relationship(back_populates="subscriptions")


class Log(SQLModel, table=True):
    """
    Модель для логирования запросов и команд пользователей.

    Attributes:
        id (Optional[int]): Уникальный идентификатор записи лога.
                           Автоматически генерируется (Primary Key).
        user_id (Optional[int]): Идентификатор пользователя, совершившего запрос.
                                 Внешний ключ к таблице пользователей.
        command (str): Команда Telegram или тип запроса (например, "/weather", "subscribed_news").
        details (Optional[str]): Дополнительные детали запроса (например, аргументы команды).
                                 Может храниться в формате JSON.
        timestamp (datetime): Дата и время выполнения запроса.
                              Хранится в формате UTC.
        user (User): Пользователь, совершивший этот запрос.
                     Устанавливается через Relationship.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    # Внешний ключ, nullable=True, так как в теории лог может быть связан
    # с запросом от неизвестного пользователя, хотя в нашем случае это маловероятно
    # после реализации регистрации по /start. Но для общности можно оставить Optional/nullable=True.
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)

    command: str = Field(index=True) # Команда или тип действия (например, 'start', 'weather', 'subscribe')
    details: Optional[str] = None # Дополнительные детали запроса (например, 'city=London', 'category=sport')

    # Время выполнения запроса. Используем default_factory для автоматической установки
    # текущего времени в UTC при создании записи.
    timestamp: datetime = Field(default_factory=lambda: datetime.now(pytz.utc))

    # Отношение к модели User. 'back_populates="logs"' связывает это отношение
    # с атрибутом 'logs' в модели User.
    user: Optional["User"] = Relationship(back_populates="logs")