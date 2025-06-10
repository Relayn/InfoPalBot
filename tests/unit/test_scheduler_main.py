import pytest
from unittest.mock import MagicMock, patch, ANY, PropertyMock
from aiogram import Bot

# Импортируем тестируемый модуль и его компоненты
from app.scheduler import main as scheduler_main_module
from app.scheduler.main import (
    set_bot_instance,
    schedule_jobs,
    shutdown_scheduler,
    scheduler,  # Глобальный экземпляр AsyncIOScheduler
    _bot_instance,  # Глобальная переменная для экземпляра бота
)

# Импортируем задачи, чтобы проверить, что они передаются в add_job
from app.scheduler.tasks import (
    test_scheduled_task,
    send_weather_updates,
    send_news_updates,
    send_events_updates,
)


@pytest.fixture(autouse=True)
def reset_global_scheduler_state():
    """
    Эта фикстура будет автоматически сбрасывать состояние глобальных переменных
    в модуле scheduler_main перед каждым тестом.
    """
    original_bot_instance = scheduler_main_module._bot_instance
    original_scheduler_jobs = list(
        scheduler_main_module.scheduler.get_jobs()
    )  # Копируем список джобов

    # Очищаем существующие джобы из глобального шедулера, если они есть от предыдущих тестов
    for job in original_scheduler_jobs:
        if scheduler_main_module.scheduler.get_job(
            job.id
        ):  # Проверяем, существует ли еще джоб
            scheduler_main_module.scheduler.remove_job(job.id)

    scheduler_main_module._bot_instance = None  # Сбрасываем экземпляр бота

    yield  # Тест выполняется здесь

    # Восстанавливаем исходное состояние после теста (хотя для _bot_instance это может быть не так критично)
    scheduler_main_module._bot_instance = original_bot_instance
    # Восстанавливать джобы не будем, т.к. каждый тест должен работать с чистым планировщиком


def test_set_bot_instance():
    """Тест: функция set_bot_instance корректно устанавливает _bot_instance."""
    mock_bot = MagicMock(spec=Bot)

    with patch.object(scheduler_main_module, "logger") as mock_logger:
        set_bot_instance(mock_bot)
        assert scheduler_main_module._bot_instance == mock_bot
        mock_logger.info.assert_called_once_with(
            "Экземпляр бота установлен для планировщика."
        )

    # Сброс для чистоты после теста, хотя фикстура reset_global_scheduler_state это делает
    scheduler_main_module._bot_instance = None


@patch.object(scheduler_main_module.scheduler, "add_job", MagicMock())
@patch.object(scheduler_main_module.scheduler, "get_job", MagicMock(return_value=None))
def test_schedule_jobs_all_added_successfully():
    """
    Тест: schedule_jobs добавляет все задачи-диспетчеры, когда _bot_instance установлен
    и задачи еще не существуют.
    """
    mock_bot = MagicMock(spec=Bot)
    scheduler_main_module._bot_instance = mock_bot

    with patch.object(scheduler_main_module, "logger"):
        schedule_jobs()

        # Теперь у нас 3 задачи-диспетчера
        assert scheduler_main_module.scheduler.get_job.call_count == 3
        scheduler_main_module.scheduler.get_job.assert_any_call("weather_dispatcher")
        scheduler_main_module.scheduler.get_job.assert_any_call("news_dispatcher")
        scheduler_main_module.scheduler.get_job.assert_any_call("events_dispatcher")

        assert scheduler_main_module.scheduler.add_job.call_count == 3

        call_args_list = scheduler_main_module.scheduler.add_job.call_args_list
        added_jobs = {call.kwargs["id"]: call for call in call_args_list}

        expected_jobs = {
            "weather_dispatcher": send_weather_updates,
            "news_dispatcher": send_news_updates,
            "events_dispatcher": send_events_updates,
        }

        for job_id, expected_func in expected_jobs.items():
            call = added_jobs.get(job_id)
            assert call is not None, f"Задача '{job_id}' не найдена"
            assert call.args[0] == expected_func
            assert call.args[1] == "interval"
            assert call.kwargs["args"] == [mock_bot]
            assert call.kwargs["minutes"] == 5

    scheduler_main_module._bot_instance = None


@patch.object(scheduler_main_module.scheduler, "add_job", MagicMock())
@patch.object(
    scheduler_main_module.scheduler, "get_job", MagicMock(return_value=MagicMock())
)  # get_job возвращает мок (джоб существует)
def test_schedule_jobs_not_added_if_exist():
    """
    Тест: schedule_jobs не добавляет задачи, если они уже существуют (get_job возвращает мок).
    """
    mock_bot = MagicMock(spec=Bot)
    scheduler_main_module._bot_instance = mock_bot

    schedule_jobs()
    scheduler_main_module.scheduler.add_job.assert_not_called()  # add_job не должен вызываться

    scheduler_main_module._bot_instance = None  # Сброс


def test_schedule_jobs_no_bot_instance():
    """
    Тест: задачи рассылок не добавляются, если _bot_instance is None.
    """
    scheduler_main_module._bot_instance = None

    with patch.object(
        scheduler_main_module.scheduler, "add_job", MagicMock()
    ) as mock_add_job, patch.object(
        scheduler_main_module.scheduler, "get_job", return_value=None
    ), patch.object(
        scheduler_main_module, "logger"
    ) as mock_logger:

        schedule_jobs()

        mock_logger.warning.assert_called_once_with(
            "Экземпляр бота не установлен. Задачи рассылок не могут быть добавлены."
        )
        mock_add_job.assert_not_called()

    scheduler_main_module._bot_instance = None


@patch.object(scheduler_main_module.scheduler, "shutdown", MagicMock())
def test_shutdown_scheduler_when_running():
    """Тест: shutdown_scheduler вызывает scheduler.shutdown(), если планировщик запущен."""
    with patch.object(
        scheduler_main_module.scheduler.__class__,
        "running",
        new_callable=PropertyMock,
        return_value=True,
    ) as mock_running_prop, patch.object(
        scheduler_main_module, "logger"
    ) as mock_logger:
        # Важно патчить на уровне класса (__class__), чтобы PropertyMock сработал для экземпляра
        # mock_running_prop здесь не используется, но показывает, что свойство было заменено
        shutdown_scheduler()
        scheduler_main_module.scheduler.shutdown.assert_called_once_with()
        mock_logger.info.assert_called_once_with(
            "Планировщик APScheduler успешно остановлен."
        )


@patch.object(scheduler_main_module.scheduler, "shutdown", MagicMock())
def test_shutdown_scheduler_when_not_running():
    """Тест: shutdown_scheduler не вызывает scheduler.shutdown(), если планировщик не запущен."""
    with patch.object(
        scheduler_main_module.scheduler.__class__,
        "running",
        new_callable=PropertyMock,
        return_value=False,
    ) as mock_running_prop, patch.object(
        scheduler_main_module, "logger"
    ) as mock_logger:
        shutdown_scheduler()
        scheduler_main_module.scheduler.shutdown.assert_not_called()
        mock_logger.info.assert_called_once_with(
            "Планировщик не был запущен или уже остановлен."
        )
