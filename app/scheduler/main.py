"""Модуль управления планировщиком задач APScheduler.

Этот модуль отвечает за инициализацию, конфигурацию, запуск и остановку
планировщика задач. Он также содержит логику для загрузки и планирования
задач на основе активных подписок из базы данных при старте приложения.

Ключевые компоненты:
- `scheduler`: Глобальный экземпляр AsyncIOScheduler.
- `set_bot_instance()`: Устанавливает экземпляр бота для использования в задачах.
- `schedule_jobs()`: Загружает активные подписки из БД и планирует их.
- `shutdown_scheduler()`: Корректно останавливает планировщик.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database.models import Subscription
from app.database.session import get_session
from .tasks import send_single_notification

logger = logging.getLogger(__name__)

_bot_instance: Optional[Bot] = None
jobstores = {"default": MemoryJobStore()}
executors = {"default": AsyncIOExecutor()}
job_defaults = {"coalesce": False, "max_instances": 3}
scheduler = AsyncIOScheduler(
    jobstores=jobstores,
    executors=executors,
    job_defaults=job_defaults,
    timezone="UTC",
)


def set_bot_instance(bot: Bot):
    """Сохраняет глобальный экземпляр бота и конфигурирует планировщик.

    Эта функция необходима, чтобы передать активный экземпляр `aiogram.Bot`
    в задачи, выполняемые планировщиком, так как они не имеют прямого
    доступа к нему.

    Args:
        bot: Экземпляр `aiogram.Bot` для использования в задачах.
    """
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = bot
        scheduler.configure(job_defaults={"kwargs": {"bot": _bot_instance}})
        logger.info("Экземпляр бота установлен для планировщика.")


def schedule_jobs():
    """Загружает активные подписки из БД и планирует для них задачи.

    Функция итерирует по всем активным подпискам и создает для каждой
    соответствующую задачу в APScheduler, используя либо интервальный,
    либо cron-триггер.
    """
    if _bot_instance is None:
        logger.error("Экземпляр бота не установлен. Планирование задач невозможно.")
        return

    logger.info("Начало динамического планирования задач из БД...")
    try:
        with get_session() as session:
            active_subscriptions = (
                session.query(Subscription)
                .filter(Subscription.status == "active")
                .all()
            )

            if not active_subscriptions:
                logger.info(
                    "Активных подписок в БД не найдено. Новые задачи не запланированы."
                )
                return

            for sub in active_subscriptions:
                job_id = f"sub_{sub.id}"
                job_params = {}

                if sub.frequency:
                    job_params = {"trigger": "interval", "hours": sub.frequency}
                    log_msg = f"интервалом {sub.frequency} ч."
                elif sub.cron_expression:
                    parts = sub.cron_expression.split()
                    job_params = {
                        "trigger": "cron",
                        "minute": int(parts[0]),
                        "hour": int(parts[1]),
                    }
                    log_msg = f"расписанием cron: '{sub.cron_expression}'"
                else:
                    logger.warning(
                        f"Подписка ID {sub.id} не имеет ни frequency, "
                        f"ни cron_expression. Пропуск."
                    )
                    continue

                try:
                    job_kwargs = {
                        "bot": _bot_instance,
                        "subscription_id": sub.id,
                    }
                    scheduler.add_job(
                        send_single_notification,
                        id=job_id,
                        kwargs=job_kwargs,
                        replace_existing=True,
                        next_run_time=datetime.now(timezone.utc),
                        **job_params,
                    )
                    logger.info(
                        f"Задача {job_id} для подписки (type: {sub.info_type}, "
                        f"user: {sub.user_id}) запланирована с {log_msg}"
                    )
                except Exception as e:
                    logger.error(
                        f"Ошибка при добавлении задачи {job_id} в планировщик: {e}",
                        exc_info=True,
                    )

            logger.info(
                "Планирование завершено. Всего запланировано/обновлено "
                f"{len(active_subscriptions)} задач."
            )

    except Exception as e:
        logger.error(
            f"Критическая ошибка при получении подписок из БД для планирования: {e}",
            exc_info=True,
        )


def shutdown_scheduler():
    """Корректно останавливает планировщик, если он запущен."""
    if scheduler.running:
        try:
            scheduler.shutdown()
            logger.info("Планировщик APScheduler успешно остановлен.")
        except Exception as e:
            logger.error(f"Ошибка при остановке планировщика: {e}", exc_info=True)
    else:
        logger.info("Планировщик APScheduler не был запущен, остановка не требуется.")