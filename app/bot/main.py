"""
Главный модуль запуска Telegram-бота InfoPalBot.

Этот файл отвечает за:
- Настройку и конфигурацию логирования.
- Инициализацию объектов Bot и Dispatcher из библиотеки aiogram.
- Регистрацию обработчиков (хендлеров) из соответствующих модулей.
- Определение и регистрацию функций, выполняемых при старте (on_startup)
  и завершении работы (on_shutdown) бота.
- Управление жизненным циклом планировщика задач APScheduler.
- Установку команд меню бота.
- Запуск процесса поллинга для получения обновлений от Telegram.
"""
import logging
import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.scheduler.main import set_bot_instance, schedule_jobs, scheduler as aps_scheduler, shutdown_scheduler

from app.bot.handlers import basic, info_requests, subscription, profile

# Настройка логирования
logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
default_bot_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=default_bot_properties)
dp = Dispatcher()


async def on_startup():
    """
    Выполняется при запуске бота.
    """
    logger.info("Бот запускается...")

    # Настройка команд меню бота
    commands_to_set = [
        types.BotCommand(command="start", description="🚀 Запуск и регистрация"),
        types.BotCommand(command="help", description="❓ Помощь по командам"),
        types.BotCommand(command="profile", description="👤 Мой профиль и подписки"),
        types.BotCommand(command="weather", description="☀️ Узнать погоду (город)"),
        types.BotCommand(command="news", description="📰 Последние новости (Россия)"),
        types.BotCommand(command="events", description="🎉 События (город)"),
        types.BotCommand(command="subscribe", description="🔔 Подписаться на рассылку"),
        types.BotCommand(command="mysubscriptions", description="📜 Мои подписки (старый)"),
        types.BotCommand(command="unsubscribe", description="🔕 Отписаться (старый)"),
        types.BotCommand(command="cancel", description="❌ Отменить текущее действие"),
    ]
    try:
        await bot.set_my_commands(commands_to_set)
        logger.info("Команды бота успешно установлены.")
    except Exception as e:
        logger.error(f"Ошибка при установке команд бота: {e}", exc_info=True)

    # Запуск планировщика
    set_bot_instance(bot)
    schedule_jobs()
    if not aps_scheduler.running:
        aps_scheduler.start()
        logger.info("Планировщик APScheduler запущен.")

    logger.info("Бот успешно запущен!")


def on_shutdown():
    """
    Выполняется при остановке бота.
    """
    logger.info("Бот останавливается...")
    shutdown_scheduler()
    logger.info("Бот остановлен.")


def main():
    """
    Главная функция для запуска бота.
    """
    # Подключаем роутеры из модулей handlers
    dp.include_router(basic.router)
    dp.include_router(info_requests.router)
    dp.include_router(subscription.router)
    dp.include_router(profile.router)

    # Регистрируем функции жизненного цикла
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Запускаем поллинг
    asyncio.run(dp.start_polling(bot, skip_updates=True))


if __name__ == "__main__":
    main()