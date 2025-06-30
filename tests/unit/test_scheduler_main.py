# Файл: tests/unit/test_scheduler_main.py

import pytest
from unittest.mock import MagicMock, patch, ANY
from aiogram import Bot

# ИЗМЕНЕНО: убран PropertyMock, он здесь не нужен
# from unittest.mock import MagicMock, patch, ANY, PropertyMock

# ИЗМЕНЕНО: импортируем только то, что нужно для тестов
from app.scheduler.main import set_bot_instance, schedule_jobs, shutdown_scheduler
from app.database.models import Subscription


# В этом файле фикстура autouse не нужна, так как мы будем мокать сам планировщик
# @pytest.fixture(autouse=True)
# def reset_scheduler():
#     ...

def test_set_bot_instance():
    """
    Тест: установка экземпляра бота.
    """
    mock_bot = MagicMock(spec=Bot)
    # Патчим сам объект scheduler, чтобы проверить вызов configure
    with patch("app.scheduler.main.scheduler") as mock_scheduler:
        set_bot_instance(mock_bot)
        mock_scheduler.configure.assert_called_once_with(job_defaults={"kwargs": {"bot": mock_bot}})


@patch("app.scheduler.main.get_session")
@patch("app.scheduler.main.scheduler")  # Патчим сам планировщик
def test_schedule_jobs_with_active_subscriptions(mock_scheduler, mock_get_session):
    """
    Тест: планирование задач для активных подписок из БД.
    """
    mock_bot = MagicMock(spec=Bot)
    set_bot_instance(mock_bot)

    sub1 = Subscription(id=1, user_id=101, info_type="weather", frequency=3, status="active")
    sub2 = Subscription(id=2, user_id=102, info_type="news", frequency=6, status="active")

    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.all.return_value = [sub1, sub2]
    mock_get_session.return_value.__enter__.return_value = mock_session

    schedule_jobs()

    # Проверяем вызовы у нашего мока планировщика
    assert mock_scheduler.add_job.call_count == 2
    mock_scheduler.add_job.assert_any_call(
        ANY, trigger="interval", hours=3, id="sub_1",
        kwargs={"subscription_id": 1}, replace_existing=True, next_run_time=ANY
    )
    mock_scheduler.add_job.assert_any_call(
        ANY, trigger="interval", hours=6, id="sub_2",
        kwargs={"subscription_id": 2}, replace_existing=True, next_run_time=ANY
    )


@patch("app.scheduler.main.get_session")
@patch("app.scheduler.main.scheduler")  # Патчим сам планировщик
def test_schedule_jobs_no_active_subscriptions(mock_scheduler, mock_get_session):
    """
    Тест: нет активных подписок, ни одна задача не добавляется.
    """
    mock_bot = MagicMock(spec=Bot)
    set_bot_instance(mock_bot)

    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.all.return_value = []
    mock_get_session.return_value.__enter__.return_value = mock_session

    schedule_jobs()
    mock_scheduler.add_job.assert_not_called()


# ИЗМЕНЕНО: Полностью переписаны тесты для shutdown_scheduler
def test_shutdown_scheduler_when_running():
    """
    Тест: остановка запущенного планировщика.
    """
    with patch("app.scheduler.main.scheduler") as mock_scheduler:
        # Настраиваем наш мок
        mock_scheduler.running = True

        # Вызываем функцию
        shutdown_scheduler()

        # Проверяем, что у мока был вызван метод shutdown
        mock_scheduler.shutdown.assert_called_once()


def test_shutdown_scheduler_when_not_running():
    """
    Тест: попытка остановки незапущенного планировщика.
    """
    with patch("app.scheduler.main.scheduler") as mock_scheduler:
        # Настраиваем наш мок
        mock_scheduler.running = False

        # Вызываем функцию
        shutdown_scheduler()

        # Проверяем, что метод shutdown НЕ был вызван
        mock_scheduler.shutdown.assert_not_called()


@patch("app.scheduler.main.get_session")
@patch("app.scheduler.main.scheduler")
def test_schedule_jobs_handles_subscription_with_no_trigger(mock_scheduler, mock_get_session):
    """
    Тест: планировщик пропускает подписку без frequency и cron_expression.
    """
    # Подписка без триггера
    sub_no_trigger = Subscription(id=3, user_id=103, info_type="weather", status="active")

    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.all.return_value = [sub_no_trigger]
    mock_get_session.return_value.__enter__.return_value = mock_session

    with patch("app.scheduler.main.logger.warning") as mock_logger:
        schedule_jobs()
        mock_logger.assert_called_once_with(
            "Подписка ID 3 не имеет ни frequency, ни cron_expression. Пропуск."
        )
        mock_scheduler.add_job.assert_not_called()


@patch("app.scheduler.main.get_session")
@patch("app.scheduler.main.scheduler")
def test_schedule_jobs_handles_add_job_error(mock_scheduler, mock_get_session):
    """
    Тест: планировщик логирует ошибку, если не может добавить задачу.
    """
    sub1 = Subscription(id=4, user_id=104, info_type="weather", frequency=3, status="active")
    mock_scheduler.add_job.side_effect = Exception("Test add_job error")

    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.all.return_value = [sub1]
    mock_get_session.return_value.__enter__.return_value = mock_session

    with patch("app.scheduler.main.logger.error") as mock_logger:
        schedule_jobs()
        mock_logger.assert_called_once_with(
            "Ошибка при добавлении задачи sub_4 в планировщик: Test add_job error", exc_info=True
        )


@patch("app.scheduler.main.get_session", side_effect=Exception("DB connection failed"))
@patch("app.scheduler.main.scheduler")
def test_schedule_jobs_handles_db_error(mock_scheduler, mock_get_session):
    """
    Тест: планировщик логирует критическую ошибку при сбое подключения к БД.
    """
    with patch("app.scheduler.main.logger.error") as mock_logger:
        schedule_jobs()
        mock_logger.assert_called_once_with(
            "Критическая ошибка при получении подписок из БД для планирования: DB connection failed", exc_info=True
        )
        mock_scheduler.add_job.assert_not_called()

@patch("app.scheduler.main.logger")
def test_schedule_jobs_bot_not_set(mock_logger):
    """
    Тест: планирование не запускается, если экземпляр бота не установлен.
    """
    # Гарантируем, что _bot_instance is None для этого теста
    with patch("app.scheduler.main._bot_instance", None):
        schedule_jobs()
        mock_logger.error.assert_called_once_with(
            "Экземпляр бота не установлен. Планирование задач невозможно."
        )


@patch("app.scheduler.main.scheduler")
def test_shutdown_scheduler_not_running_logs_message(mock_scheduler):
    """
    Тест: shutdown_scheduler корректно логирует, если планировщик не запущен.
    """
    mock_scheduler.running = False
    with patch("app.scheduler.main.logger.info") as mock_logger:
        shutdown_scheduler()
        mock_logger.assert_called_with(
            "Планировщик APScheduler не был запущен, остановка не требуется."
        )