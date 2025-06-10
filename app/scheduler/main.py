"""
Модуль для инициализации и управления планировщиком задач APScheduler.
Отвечает за запуск, остановку и добавление запланированных задач.

Этот модуль обеспечивает централизованное управление всеми запланированными задачами бота,
используя APScheduler для асинхронного выполнения задач. Модуль поддерживает:

- Инициализацию и конфигурацию планировщика
- Добавление и управление задачами рассылки
- Корректное завершение работы планировщика
- Интеграцию с экземпляром бота для отправки сообщений

Основные компоненты:
- AsyncIOScheduler: асинхронный планировщик для работы с asyncio
- Глобальный экземпляр бота для задач рассылки
- Функции управления жизненным циклом планировщика

Запланированные задачи:
1. Тестовая задача (каждые 30 секунд)
2. Рассылка погоды (каждые 3 часа)
3. Рассылка новостей (каждые 6 часов)
4. Рассылка событий (каждые 2 минуты в тестовом режиме)

Пример использования:
    # В on_startup бота:
    set_bot_instance(bot)
    schedule_jobs()
    scheduler.start()

    # В on_shutdown бота:
    shutdown_scheduler()
"""

import logging
from apscheduler.schedulers.asyncio import (
    AsyncIOScheduler,
)  # Асинхронный планировщик для asyncio
from aiogram import Bot  # Для передачи экземпляра бота в задачи рассылки
from typing import Optional  # Для аннотации типа Optional

# Импортируем все задачи, которые будут планироваться
from app.scheduler.tasks import (
    test_scheduled_task,
    send_weather_updates,
    send_news_updates,
    send_events_updates,
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


def set_bot_instance(bot: Bot) -> None:
    """
    Устанавливает экземпляр Aiogram Bot для использования в задачах планировщика.
    Эта функция должна быть вызвана в on_startup бота перед добавлением задач.

    Args:
        bot (Bot): Экземпляр бота Aiogram, который будет использоваться
                  для отправки сообщений в задачах рассылки.

    Note:
        - Функция должна быть вызвана до schedule_jobs()
        - Без установленного экземпляра бота задачи рассылки не будут добавлены
        - Экземпляр бота хранится в глобальной переменной _bot_instance
    """
    global _bot_instance
    _bot_instance = bot
    logger.info("Экземпляр бота установлен для планировщика.")


def schedule_jobs() -> None:
    """
    Добавляет все необходимые задачи в планировщик.
    Задачи добавляются только один раз, если они еще не существуют в планировщике.
    Задачи-диспетчеры запускаются каждые 5 минут и сами определяют,
    какие уведомления пора отправлять на основе настроек частоты подписок.
    """
    if _bot_instance is None:
        logger.warning(
            "Экземпляр бота не установлен. Задачи рассылок не могут быть добавлены."
        )
        return

    try:
        job_interval_minutes = 5

        if not scheduler.get_job("weather_dispatcher"):
            scheduler.add_job(
                send_weather_updates,
                "interval",
                minutes=job_interval_minutes,
                id="weather_dispatcher",
                args=[_bot_instance],
            )
            logger.info(
                f"Задача рассылки погоды добавлена (каждые {job_interval_minutes} минут)."
            )

        if not scheduler.get_job("news_dispatcher"):
            scheduler.add_job(
                send_news_updates,
                "interval",
                minutes=job_interval_minutes,
                id="news_dispatcher",
                args=[_bot_instance],
            )
            logger.info(
                f"Задача рассылки новостей добавлена (каждые {job_interval_minutes} минут)."
            )

        if not scheduler.get_job("events_dispatcher"):
            scheduler.add_job(
                send_events_updates,
                "interval",
                minutes=job_interval_minutes,
                id="events_dispatcher",
                args=[_bot_instance],
            )
            logger.info(
                f"Задача рассылки событий добавлена (каждые {job_interval_minutes} минут)."
            )

    except Exception as e:
        logger.error(f"Ошибка при добавлении задач в планировщик: {e}", exc_info=True)


def shutdown_scheduler() -> None:
    """
    Корректно останавливает планировщик APScheduler.
    Эта функция должна быть вызвана при завершении работы приложения.

    Функция:
    1. Проверяет, запущен ли планировщик
    2. Если запущен, останавливает все запланированные задачи
    3. Логирует результат операции

    Note:
        - Функция должна быть вызвана в on_shutdown бота
        - Остановка планировщика происходит в фоновом режиме
        - Все незавершенные задачи будут корректно завершены
        - После остановки планировщика новые задачи не могут быть добавлены
    """
    if scheduler.running:
        try:
            scheduler.shutdown()  # Останавливает все запланированные задачи
            logger.info("Планировщик APScheduler успешно остановлен.")
        except Exception as e:
            logger.error(f"Ошибка при остановке планировщика: {e}", exc_info=True)
    else:
        logger.info("Планировщик не был запущен или уже остановлен.")
