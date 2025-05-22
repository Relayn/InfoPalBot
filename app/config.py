from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv # Для явной загрузки .env файла

# Явно загружаем переменные из .env файла в текущее окружение.
# Это необходимо, если скрипт запускается не из корневой директории проекта,
# или если pydantic-settings не находит .env автоматически в данном контексте.
load_dotenv()

class Settings(BaseSettings):
    """
    Класс для загрузки и хранения настроек приложения из переменных окружения.
    Использует pydantic-settings для автоматической загрузки и валидации типов.

    Переменные загружаются из файла .env в корневой директории проекта.
    """
    # Конфигурация модели настроек для pydantic-settings
    model_config = SettingsConfigDict(
        env_file=".env",         # Указываем файл, из которого загружать переменные
        env_file_encoding='utf-8' # Указываем кодировку файла
    )

    # Настройки Telegram бота
    TELEGRAM_BOT_TOKEN: str      # Токен Telegram бота. Получается у @BotFather.

    # Настройки базы данных
    DATABASE_URL: str            # URL для подключения к базе данных (например, sqlite:///./app/database/infopalbot.db).

    # Ключи API внешних сервисов
    # Если ключ не указан в .env, используется пустая строка.
    WEATHER_API_KEY: str = ""    # Ключ API для сервиса погоды (например, OpenWeatherMap).
    NEWS_API_KEY: str = ""       # Ключ API для сервиса новостей (например, NewsAPI.org).
    EVENTS_API_KEY: str = ""     # Ключ API для сервиса событий (если используется, например, KudaGo не требует ключа).

    # Настройки логирования
    LOG_LEVEL: str = "INFO"      # Уровень логирования (например, "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL").

    # Опциональные настройки, которые могут быть добавлены в будущем
    # ADMIN_TELEGRAM_ID: int | None = None # Telegram ID администратора для специальных команд.

# Создаем единственный экземпляр настроек, который будет использоваться во всем приложении.
# Это обеспечивает централизованный доступ к конфигурации.
settings = Settings()