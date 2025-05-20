import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from typing import Optional

from app.scheduler.tasks import (
    test_scheduled_task,
    send_weather_updates,
    send_news_updates,
    send_events_updates
)

logger = logging.getLogger(__name__)

# Создаем экземпляр планировщика, но НЕ ЗАПУСКАЕМ его здесь
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

_bot_instance: Optional[Bot] = None


def set_bot_instance(bot: Bot):
    global _bot_instance
    _bot_instance = bot
    logger.info("Экземпляр бота установлен для планировщика.")


def schedule_jobs():  # Переименовали функцию, теперь она только добавляет задачи
    """Добавляет задачи в планировщик."""
    if _bot_instance is None and (  # Проверяем, нужны ли задачи, требующие бота
            any(job.func == send_weather_updates for job in scheduler.get_jobs()) or
            any(job.func == send_news_updates for job in scheduler.get_jobs()) or
            any(job.func == send_events_updates for job in scheduler.get_jobs())
    ):  # Эта проверка сложная, проще просто добавлять если бот есть
        logger.warning("Экземпляр бота не установлен, задачи рассылок могут не работать корректно, если уже добавлены.")
        # Но мы будем добавлять их ниже только если бот есть.

    try:
        # Убираем проверку scheduler.running, т.к. start будет вызван в on_startup
        if not scheduler.get_job('test_task'):  # Добавляем, только если еще не добавлена
            scheduler.add_job(test_scheduled_task, 'interval', seconds=30, id='test_task')
            logger.info("Тестовая задача добавлена в планировщик.")

        if _bot_instance:
            if not scheduler.get_job('weather_updates_interval'):
                scheduler.add_job(send_weather_updates, 'interval', hours=3, id='weather_updates_interval',
                                  args=[_bot_instance])
                logger.info("Задача рассылки погоды добавлена.")
            if not scheduler.get_job('news_updates_interval'):
                scheduler.add_job(send_news_updates, 'interval', hours=6, id='news_updates_interval',
                                  args=[_bot_instance])
                logger.info("Задача рассылки новостей добавлена.")
            if not scheduler.get_job('events_updates_task'):
                scheduler.add_job(send_events_updates, 'interval', minutes=2, id='events_updates_task',
                                  args=[_bot_instance])
                logger.info("Задача рассылки событий добавлена (для теста - каждые 2 минуты).")
        else:
            logger.warning("Задачи рассылок не добавлены, т.к. экземпляр бота не предоставлен.")

        # scheduler.start() # <--- УБИРАЕМ ЗАПУСК ОТСЮДА

    except Exception as e:
        logger.error(f"Ошибка при добавлении задач в планировщик: {e}", exc_info=True)


# shutdown_scheduler остается без изменений
def shutdown_scheduler():
    if scheduler.running:
        try:
            scheduler.shutdown()
            logger.info("Планировщик APScheduler успешно остановлен.")
        except Exception as e:
            logger.error(f"Ошибка при остановке планировщика: {e}", exc_info=True)
    else:
        logger.info("Планировщик не был запущен или уже остановлен.")