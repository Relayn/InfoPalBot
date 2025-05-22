"""
Модуль для инициализации и управления планировщиком задач APScheduler.
Отвечает за запуск, остановку и добавление запланированных задач.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # Асинхронный планировщик для asyncio
from aiogram import Bot  # Для передачи экземпляра бота в задачи рассылки
from typing import Optional  # Для аннотации типа Optional

# Импортируем все задачи, которые будут планироваться
from app.scheduler.tasks import (
    test_scheduled_task,
    send_weather_updates,
    send_news_updates,
    send_events_updates
)

# Настройка логгера для модуля
logger = logging.getLogger(__name__)

# Создаем глобальный экземпляр планировщика.
# Используем AsyncIOScheduler, так как бот работает на asyncio.
# Указываем часовой пояс для корректной работы cron-триггеров.
scheduler: AsyncIOScheduler = AsyncIOScheduler(timezone="Europe/Moscow")

# Глобальная переменная для хранения экземпляра бота.
# Экземпляр бота необходим задачам рассылки для отправки сообщений.
_bot_instance: Optional[Bot] = None


def set_bot_instance(bot: Bot):
    """
    Устанавливает экземпляр Aiogram Bot для использования в задачах планировщика.
    Эта функция должна быть вызвана в on_startup бота.

    Args:
        bot (Bot): Экземпляр бота Aiogram.
    """
    global _bot_instance
    _bot_instance = bot
    logger.info("Экземпляр бота установлен для планировщика.")


def schedule_jobs():
    """
    Добавляет все необходимые задачи в планировщик.
    Задачи добавляются только один раз, если они еще не существуют в планировщике.
    """
    # Если экземпляр бота не установлен, задачи рассылок не будут добавлены
    if _bot_instance is None:
        logger.warning("Экземпляр бота не установлен. Задачи рассылок не могут быть добавлены.")
        return  # Выходим, если нет бота для рассылок

    try:
        # Добавляем тестовую задачу
        if not scheduler.get_job('test_task'):
            scheduler.add_job(test_scheduled_task, 'interval', seconds=30, id='test_task')
            logger.info("Тестовая задача добавлена в планировщик (каждые 30 секунд).")

        # Добавляем задачи рассылок, передавая экземпляр бота как аргумент
        # Проверяем, что задача еще не добавлена, чтобы избежать дублирования при повторном запуске
        if not scheduler.get_job('weather_updates_interval'):
            scheduler.add_job(
                send_weather_updates,
                'interval',  # Триггер: интервал
                hours=3,  # Интервал: каждые 3 часа
                id='weather_updates_interval',
                args=[_bot_instance]  # Передаем экземпляр бота в задачу
            )
            logger.info("Задача рассылки погоды добавлена (каждые 3 часа).")

        if not scheduler.get_job('news_updates_interval'):
            scheduler.add_job(
                send_news_updates,
                'interval',  # Триггер: интервал
                hours=6,  # Интервал: каждые 6 часов
                id='news_updates_interval',
                args=[_bot_instance]  # Передаем экземпляр бота
            )
            logger.info("Задача рассылки новостей добавлена (каждые 6 часов).")

        if not scheduler.get_job('events_updates_task'):
            scheduler.add_job(
                send_events_updates,
                'interval',  # Триггер: интервал
                minutes=2,  # Интервал для теста: каждые 2 минуты. В production лучше использовать 'cron'.
                # Пример для production: 'cron', hour=9, minute=30, id='events_updates_cron'
                id='events_updates_task',
                args=[_bot_instance]  # Передаем экземпляр бота
            )
            logger.info("Задача рассылки событий добавлена (для теста - каждые 2 минуты).")

        # Планировщик стартует в on_startup функции бота, когда event loop уже запущен.
        # scheduler.start() # <-- Эту строку убрали отсюда, чтобы избежать RuntimeError: no running event loop

    except Exception as e:
        logger.error(f"Ошибка при добавлении задач в планировщик: {e}", exc_info=True)


def shutdown_scheduler():
    """
    Корректно останавливает планировщик APScheduler.
    Эта функция должна быть вызвана при завершении работы приложения.
    """
    if scheduler.running:
        try:
            scheduler.shutdown()  # Останавливает все запланированные задачи
            logger.info("Планировщик APScheduler успешно остановлен.")
        except Exception as e:
            logger.error(f"Ошибка при остановке планировщика: {e}", exc_info=True)
    else:
        logger.info("Планировщик не был запущен или уже остановлен.")