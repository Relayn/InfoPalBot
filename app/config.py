from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv # Импортируем load_dotenv

# Явно загружаем переменные из .env файла в текущее окружение.
# Это нужно, если вы запускаете этот скрипт не из корневой директории проекта.
# При обычном запуске приложения из корня, pydantic-settings сам найдет .env
load_dotenv()

class Settings(BaseSettings):
    """
    Класс для загрузки и хранения настроек приложения из переменных окружения.
    Использует pydantic-settings для автоматической загрузки и валидации.
    """
    # Параметры модели настроек
    model_config = SettingsConfigDict(
        env_file=".env",         # Указываем файл, из которого загружать переменные.
                                 # При запуске из корня проекта, это будет ./env
                                 # При запуске из app/, load_dotenv выше уже загрузил их в окружение.
        env_file_encoding='utf-8' # Указываем кодировку файла
    )

    # Настройки Telegram бота
    TELEGRAM_BOT_TOKEN: str      # Токен Telegram бота. Получается у @BotFather.

    # Настройки базы данных
    DATABASE_URL: str            # URL для подключения к базе данных.

    # Ключи API внешних сервисов
    WEATHER_API_KEY: str = ""    # Ключ API для сервиса погоды. По умолчанию пустая строка, можно сделать обязательным.
    NEWS_API_KEY: str = ""       # Ключ API для сервиса новостей.
    EVENTS_API_KEY: str = ""     # Ключ API для сервиса событий.

    # Настройки логирования
    LOG_LEVEL: str = "INFO"      # Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    # Опциональные настройки (закомментированы в .env.example)
    # ADMIN_TELEGRAM_ID: int | None = None # Telegram ID администратора (если нужен)

# Создаем экземпляр настроек, который можно будет импортировать в других модулях
settings = Settings()

# Пример использования (можно удалить после проверки)
#if __name__ == "__main__":
#    print("Загруженные настройки:")
     # В целях безопасности не выводим токен бота
#    print(f"Telegram Bot Token: {'***' if settings.TELEGRAM_BOT_TOKEN else 'Not Set'}")
#    print(f"Database URL: {settings.DATABASE_URL}")
#    print(f"Weather API Key: {'***' if settings.WEATHER_API_KEY else 'Not Set'}")
#    print(f"Log Level: {settings.LOG_LEVEL}")