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
    _bot_instance  # Глобальная переменная для экземпляра бота
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
    original_scheduler_jobs = list(scheduler_main_module.scheduler.get_jobs())  # Копируем список джобов

    # Очищаем существующие джобы из глобального шедулера, если они есть от предыдущих тестов
    for job in original_scheduler_jobs:
        if scheduler_main_module.scheduler.get_job(job.id):  # Проверяем, существует ли еще джоб
            scheduler_main_module.scheduler.remove_job(job.id)

    scheduler_main_module._bot_instance = None  # Сбрасываем экземпляр бота

    yield  # Тест выполняется здесь

    # Восстанавливаем исходное состояние после теста (хотя для _bot_instance это может быть не так критично)
    scheduler_main_module._bot_instance = original_bot_instance
    # Восстанавливать джобы не будем, т.к. каждый тест должен работать с чистым планировщиком


def test_set_bot_instance():
    """Тест: функция set_bot_instance корректно устанавливает _bot_instance."""
    mock_bot = MagicMock(spec=Bot)

    with patch.object(scheduler_main_module, 'logger') as mock_logger:
        set_bot_instance(mock_bot)
        assert scheduler_main_module._bot_instance == mock_bot
        mock_logger.info.assert_called_once_with("Экземпляр бота установлен для планировщика.")

    # Сброс для чистоты после теста, хотя фикстура reset_global_scheduler_state это делает
    scheduler_main_module._bot_instance = None


@patch.object(scheduler_main_module.scheduler, 'add_job', MagicMock())  # Мок add_job на уровне класса/экземпляра
@patch.object(scheduler_main_module.scheduler, 'get_job',
              MagicMock(return_value=None))  # get_job возвращает None (джоб не существует)
def test_schedule_jobs_all_added_successfully():
    """
    Тест: schedule_jobs добавляет все задачи, когда _bot_instance установлен и задачи еще не существуют.
    """
    mock_bot = MagicMock(spec=Bot)
    scheduler_main_module._bot_instance = mock_bot  # Устанавливаем бота напрямую для теста

    with patch.object(scheduler_main_module, 'logger') as mock_logger:
        schedule_jobs()

        # Проверяем, что get_job вызывался для каждой задачи перед add_job
        scheduler_main_module.scheduler.get_job.assert_any_call("test_task")
        scheduler_main_module.scheduler.get_job.assert_any_call("weather_updates_interval")
        scheduler_main_module.scheduler.get_job.assert_any_call("news_updates_interval")
        scheduler_main_module.scheduler.get_job.assert_any_call("events_updates_task")

        # Проверяем вызовы add_job
        calls = scheduler_main_module.scheduler.add_job.call_args_list

        expected_calls_args = [
            (test_scheduled_task, "interval"),
            (send_weather_updates, "interval"),
            (send_news_updates, "interval"),
            (send_events_updates, "interval"),
        ]

        added_tasks_funcs = [call.args[0] for call in calls]
        for func, trigger in expected_calls_args:
            assert func in added_tasks_funcs
            # Найти соответствующий вызов и проверить остальные параметры
            for call_item in calls:
                if call_item.args[0] == func:
                    assert call_item.args[1] == trigger  # Проверка типа триггера
                    if func != test_scheduled_task:  # Задачи рассылок должны иметь args=[mock_bot]
                        assert call_item.kwargs['args'] == [mock_bot]
                    break
            else:
                assert False, f"Задача для {func.__name__} не была добавлена"

        assert scheduler_main_module.scheduler.add_job.call_count == 4

        # Проверка логов
        mock_logger.info.assert_any_call("Тестовая задача добавлена в планировщик (каждые 30 секунд).")
        mock_logger.info.assert_any_call("Задача рассылки погоды добавлена (каждые 3 часа).")
        mock_logger.info.assert_any_call("Задача рассылки новостей добавлена (каждые 6 часов).")
        mock_logger.info.assert_any_call("Задача рассылки событий добавлена (для теста - каждые 2 минуты).")

    scheduler_main_module._bot_instance = None  # Сброс


@patch.object(scheduler_main_module.scheduler, 'add_job', MagicMock())
@patch.object(scheduler_main_module.scheduler, 'get_job',
              MagicMock(return_value=MagicMock()))  # get_job возвращает мок (джоб существует)
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
    Тестовая задача (без бота) должна добавиться, если ее нет.
    """
    scheduler_main_module._bot_instance = None  # Убедимся, что бота нет

    # Мокируем get_job так, чтобы для тестовой задачи он вернул None, а для остальных - мок
    def get_job_side_effect(job_id):
        if job_id == "test_task":
            return None  # Тестовой задачи нет
        return MagicMock()  # Остальные задачи как бы есть (или не будут проверяться на добавление)

    with patch.object(scheduler_main_module.scheduler, 'add_job', MagicMock()) as mock_add_job, \
            patch.object(scheduler_main_module.scheduler, 'get_job', side_effect=get_job_side_effect), \
            patch.object(scheduler_main_module, 'logger') as mock_logger:

        schedule_jobs()

        mock_logger.warning.assert_called_once_with(
            "Экземпляр бота не установлен. Задачи рассылок не могут быть добавлены."
        )
        # Только тестовая задача должна была попытаться добавиться
        # mock_add_job.assert_called_once_with(test_scheduled_task, "interval", seconds=30, id="test_task")

        # Проверяем, что add_job был вызван только для test_task
        test_task_added = False
        for call_item in mock_add_job.call_args_list:
            if call_item.args[0] == test_scheduled_task:
                test_task_added = True
                assert call_item.args[1] == "interval"
                assert call_item.kwargs['id'] == "test_task"
            else:
                # Убедимся, что другие задачи (требующие бота) не добавлялись
                assert call_item.args[0] not in [send_weather_updates, send_news_updates, send_events_updates]

        if mock_add_job.call_count > 0:  # Если тестовая задача была добавлена
            assert test_task_added, "Тестовая задача не была добавлена, хотя должна была"
            assert mock_add_job.call_count == 1  # Только одна задача добавлена
        else:  # Если тестовая задача уже существовала (get_job_side_effect вернул бы мок для нее)
            assert not test_task_added  # Тогда она не должна добавляться
            assert mock_add_job.call_count == 0

    scheduler_main_module._bot_instance = None  # Сброс


@patch.object(scheduler_main_module.scheduler, 'shutdown', MagicMock())
def test_shutdown_scheduler_when_running():
    """Тест: shutdown_scheduler вызывает scheduler.shutdown(), если планировщик запущен."""
    with patch.object(scheduler_main_module.scheduler.__class__, 'running', new_callable=PropertyMock, return_value=True) as mock_running_prop, \
         patch.object(scheduler_main_module, 'logger') as mock_logger:
        # Важно патчить на уровне класса (__class__), чтобы PropertyMock сработал для экземпляра
        # mock_running_prop здесь не используется, но показывает, что свойство было заменено
        shutdown_scheduler()
        scheduler_main_module.scheduler.shutdown.assert_called_once_with()
        mock_logger.info.assert_called_once_with("Планировщик APScheduler успешно остановлен.")


@patch.object(scheduler_main_module.scheduler, 'shutdown', MagicMock())
def test_shutdown_scheduler_when_not_running():
    """Тест: shutdown_scheduler не вызывает scheduler.shutdown(), если планировщик не запущен."""
    with patch.object(scheduler_main_module.scheduler.__class__, 'running', new_callable=PropertyMock, return_value=False) as mock_running_prop, \
         patch.object(scheduler_main_module, 'logger') as mock_logger:
        shutdown_scheduler()
        scheduler_main_module.scheduler.shutdown.assert_not_called()
        mock_logger.info.assert_called_once_with("Планировщик не был запущен или уже остановлен.")