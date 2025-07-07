"""
Модуль конфигурации приложения.
Использует pydantic-settings для загрузки и валидации настроек из переменных окружения.

Этот модуль:
1. Загружает переменные из .env файла
2. Определяет структуру настроек приложения
3. Создает глобальный экземпляр настроек
4. Обеспечивает типизацию и валидацию всех настроек

Пример использования:
    from app.config import settings
    bot_token = settings.TELEGRAM_BOT_TOKEN
    db_url = settings.DATABASE_URL
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """
    Класс для загрузки и хранения настроек приложения.

    Использует pydantic-settings для автоматической загрузки и валидации
    переменных из файла .env и системного окружения.

    Attributes:
        TELEGRAM_BOT_TOKEN: Токен Telegram бота от @BotFather.
        DATABASE_URL: URL для подключения к базе данных.
        WEATHER_API_KEY: Ключ API для OpenWeatherMap.
        NEWS_API_KEY: Ключ API для NewsAPI.org.
        EVENTS_API_KEY: Ключ API для сервиса событий (не используется KudaGo).
        LOG_LEVEL: Уровень логирования (e.g., "INFO", "DEBUG").

    model_config (SettingsConfigDict): Конфигурация для pydantic,
        указывающая на использование файла .env.
    """

    # Конфигурация модели настроек для pydantic-settings
    model_config = SettingsConfigDict(
        env_file=".env",  # Указываем файл, из которого загружать переменные
        env_file_encoding="utf-8",  # Указываем кодировку файла
    )

    # Настройки Telegram бота
    TELEGRAM_BOT_TOKEN: str
    # Обязательное поле, без него бот не запустится.

    # Настройки базы данных
    DATABASE_URL: str
    # Формат: sqlite:///./app/database/infopalbot.db
    # Обязательное поле, без него приложение не запустится.

    # Ключи API внешних сервисов
    # Если ключ не указан в .env, используется пустая строка.
    # При отсутствии ключа соответствующий функционал будет недоступен.
    WEATHER_API_KEY: str = ""
    NEWS_API_KEY: str = ""
    EVENTS_API_KEY: str = ""  # Зарезервировано, KudaGo не требует ключа.

    # Настройки логирования
    LOG_LEVEL: str = "INFO"


# Создаем единственный экземпляр настроек, который будет использоваться во всем приложении.
# Это обеспечивает централизованный доступ к конфигурации и соблюдение паттерна Singleton.
settings = Settings()
