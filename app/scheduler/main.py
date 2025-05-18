import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from typing import Optional

# Импортируем все задачи
from app.scheduler.tasks import (
    test_scheduled_task,
    send_weather_updates,
    send_news_updates,
    send_events_updates
)

logger = logging.getLogger(__name__)

# Создаем экземпляр планировщика
scheduler = AsyncIOScheduler(timezone="Europe/Moscow") # Указываем часовой пояс

# Глобальная переменная для хранения экземпляра бота
_bot_instance: Optional[Bot] = None

def set_bot_instance(bot: Bot):
    """Устанавливает экземпляр бота для использования в задачах планировщика."""
    global _bot_instance
    _bot_instance = bot
    logger.info("Экземпляр бота установлен для планировщика.")

def init_scheduler():
    """
    Инициализирует и запускает планировщик с задачами.
    """
    if scheduler.running:
        logger.info("Планировщик уже запущен.")
        return

    if _bot_instance is None:
        logger.error("Экземпляр бота не установлен для планировщика. Рассылки не будут работать.")
        # Можно решить, запускать ли планировщик вообще без бота
        # return

    try:
        # Добавляем тестовую задачу: выполняется каждые 30 секунд
        scheduler.add_job(test_scheduled_task, 'interval', seconds=30, id='test_task')
        logger.info("Тестовая задача добавлена в планировщик (каждые 30 секунд).")

        if _bot_instance: # Добавляем задачи, требующие бота, только если он есть
            # Рассылка погоды (например, каждые 3 часа)
            scheduler.add_job(
                send_weather_updates,
                'interval',
                hours=3,
                id='weather_updates_interval',
                args=[_bot_instance]
            )
            logger.info("Задача рассылки погоды добавлена (каждые 3 часа).")

            # Рассылка новостей (например, каждые 6 часов)
            scheduler.add_job(
                send_news_updates,
                'interval',
                hours=6,
                id='news_updates_interval',
                args=[_bot_instance]
            )
            logger.info("Задача рассылки новостей добавлена (каждые 6 часов).")

            # Рассылка событий (например, раз в день утром, для теста - каждые 2 минуты)
            scheduler.add_job(
                send_events_updates,
                'interval', # Для теста можно использовать 'interval'
                hour=24,  # Для теста - каждые 2 минуты
                # 'cron', hour=9, minute=30, # Пример для ежедневной рассылки
                id='events_updates_task', # Изменил id на более общий
                args=[_bot_instance]
            )
            logger.info("Задача рассылки событий добавлена (для теста - каждые 2 минуты).")
        else:
            logger.warning("Задачи рассылок не добавлены, т.к. экземпляр бота не предоставлен.")

        scheduler.start()
        logger.info("Планировщик APScheduler успешно запущен.")

    except Exception as e:
        logger.error(f"Ошибка при инициализации или запуске планировщика: {e}", exc_info=True)

def shutdown_scheduler():
    """
    Корректно останавливает планировщик.
    """
    if scheduler.running:
        try:
            scheduler.shutdown()
            logger.info("Планировщик APScheduler успешно остановлен.")
        except Exception as e:
            logger.error(f"Ошибка при остановке планировщика: {e}", exc_info=True)
    else:
        logger.info("Планировщик не был запущен.")