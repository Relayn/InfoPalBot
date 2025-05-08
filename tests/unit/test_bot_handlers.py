import pytest
import html # импортируем httpx для escape
from unittest.mock import AsyncMock, MagicMock, patch

# Импортируем тестируемые обработчики
from app.bot.main import (
    process_start_command,
    process_help_command,
    process_weather_command,
    process_news_command
)
# Импортируем модель User из БД и переименовываем
from app.database.models import User as DBUser
# Импортируем типы aiogram и CommandObject
from aiogram.types import Message, User as AiogramUser, Chat
from aiogram.filters import CommandObject
# Импортируем модель Settings для мокирования настроек
from app.config import Settings

# --- Тесты для process_start_command ---

@pytest.mark.asyncio
async def test_process_start_command_new_user():
    """
    Тест: команда /start для нового пользователя.
    Ожидается:
    - Вызов create_user_if_not_exists.
    - Отправка приветственного сообщения.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser)
    mock_message.from_user.id = 12345
    mock_message.from_user.full_name = "Test User"
    mock_message.chat = MagicMock(spec=Chat)
    mock_message.chat.id = 12345

    mock_db_user = DBUser(id=1, telegram_id=12345)

    with patch('app.bot.main.get_session') as mock_get_session, \
         patch('app.bot.main.create_user_if_not_exists', return_value=mock_db_user) as mock_create_user:

        mock_session_context_manager = MagicMock()
        mock_session = MagicMock()
        mock_session_context_manager.__enter__.return_value = mock_session
        mock_get_session.return_value.__next__.return_value = mock_session_context_manager

        await process_start_command(mock_message)

        mock_create_user.assert_called_once_with(session=mock_session, telegram_id=12345)
        expected_reply_text = (
            f"Привет, {mock_message.from_user.full_name}! Я InfoPalBot. "
            f"Я могу предоставить тебе актуальную информацию.\n"
            f"Используй /help, чтобы увидеть список доступных команд."
        )
        mock_message.answer.assert_called_once_with(expected_reply_text)


@pytest.mark.asyncio
async def test_process_start_command_existing_user():
    """
    Тест: команда /start для существующего пользователя.
    Ожидается:
    - Вызов create_user_if_not_exists (которая вернет существующего пользователя).
    - Отправка приветственного сообщения.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser)
    mock_message.from_user.id = 54321
    mock_message.from_user.full_name = "Existing User"
    mock_message.chat = MagicMock(spec=Chat)
    mock_message.chat.id = 54321

    mock_db_user = DBUser(id=2, telegram_id=54321)

    with patch('app.bot.main.get_session') as mock_get_session, \
         patch('app.bot.main.create_user_if_not_exists', return_value=mock_db_user) as mock_create_user:

        mock_session_context_manager = MagicMock()
        mock_session = MagicMock()
        mock_session_context_manager.__enter__.return_value = mock_session
        mock_get_session.return_value.__next__.return_value = mock_session_context_manager

        await process_start_command(mock_message)

        mock_create_user.assert_called_once_with(session=mock_session, telegram_id=54321)
        expected_reply_text = (
            f"Привет, {mock_message.from_user.full_name}! Я InfoPalBot. "
            f"Я могу предоставить тебе актуальную информацию.\n"
            f"Используй /help, чтобы увидеть список доступных команд."
        )
        mock_message.answer.assert_called_once_with(expected_reply_text)


@pytest.mark.asyncio
async def test_process_start_command_db_error():
    """
    Тест: команда /start с ошибкой при работе с БД.
    Ожидается:
    - Отправка сообщения об ошибке пользователю.
    - Логирование ошибки.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser)
    mock_message.from_user.id = 67890
    mock_message.from_user.full_name = "Error User"
    mock_message.chat = MagicMock(spec=Chat)
    mock_message.chat.id = 67890

    db_exception = Exception("Тестовая ошибка БД")

    with patch('app.bot.main.get_session') as mock_get_session, \
         patch('app.bot.main.create_user_if_not_exists', side_effect=db_exception) as mock_create_user, \
         patch('app.bot.main.logger.error') as mock_logger_error:

        mock_session_context_manager = MagicMock()
        mock_session = MagicMock()
        mock_session_context_manager.__enter__.return_value = mock_session
        mock_get_session.return_value.__next__.return_value = mock_session_context_manager

        await process_start_command(mock_message)

        mock_create_user.assert_called_once_with(session=mock_session, telegram_id=67890)
        mock_message.answer.assert_called_once_with("Произошла ошибка при обработке вашего запроса. Попробуйте позже.")
        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        assert f"Ошибка при обработке команды /start для пользователя {mock_message.from_user.id}: {db_exception}" in args[0]
        assert kwargs.get('exc_info') is True


# --- Тесты для process_help_command ---

@pytest.mark.asyncio
async def test_process_help_command():
    """
    Тест: команда /help.
    Ожидается:
    - Отправка текста справки.
    - Логирование действия.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser)
    mock_message.from_user.id = 11223

    with patch('app.bot.main.logger.info') as mock_logger_info:
        await process_help_command(mock_message)

        expected_help_text = (
            "<b>Доступные команды:</b>\n"
            "<code>/start</code> - Начать работу с ботом и зарегистрироваться\n"
            "<code>/help</code> - Показать это сообщение со справкой\n"
            "<code>/weather [город]</code> - Получить текущий прогноз погоды (например, <code>/weather Москва</code>)\n"
            "<code>/news</code> - Получить последние новости (Россия)\n" # Уточнил описание, как в коде бота
            "<code>/events</code> - Узнать о предстоящих событиях (в разработке)\n"
            "\n"
            "<b>Подписки (в разработке):</b>\n"
            "<code>/subscribe</code> - Подписаться на рассылку\n"
            "<code>/unsubscribe</code> - Отписаться от рассылки\n"
            "<code>/mysubscriptions</code> - Посмотреть мои подписки\n"
        )
        mock_message.answer.assert_called_once_with(expected_help_text)
        mock_logger_info.assert_called_with(f"Отправлена справка по команде /help пользователю {mock_message.from_user.id}")


# --- Тесты для process_weather_command ---

@pytest.mark.asyncio
async def test_process_weather_command_success():
    """
    Тест: успешное получение погоды по команде /weather.
    """
    city_name = "Москва"
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123, full_name="Tester")
    mock_command = MagicMock(spec=CommandObject, args=city_name)

    mock_weather_api_response = {
        "weather": [{"description": "ясно"}],
        "main": {"temp": 20.5, "feels_like": 19.0, "humidity": 50},
        "wind": {"speed": 3.0, "deg": 180},
        "name": "Москва"
    }

    with patch('app.bot.main.get_weather_data', return_value=mock_weather_api_response) as mock_get_weather, \
         patch('app.bot.main.logger') as mock_logger:

        await process_weather_command(mock_message, mock_command)

        mock_message.reply.assert_any_call(f"Запрашиваю погоду для города <b>{city_name}</b>...")
        mock_get_weather.assert_called_once_with(city_name.strip())

        expected_response_text = (
            f"<b>Погода в городе {mock_weather_api_response.get('name', city_name)}:</b>\n"
            f"🌡️ Температура: {mock_weather_api_response['main']['temp']}°C (ощущается как {mock_weather_api_response['main']['feels_like']}°C)\n"
            f"💧 Влажность: {mock_weather_api_response['main']['humidity']}%\n"
            f"💨 Ветер: {mock_weather_api_response['wind']['speed']} м/с, Южный\n"
            f"☀️ Описание: Ясно"
        )
        mock_message.answer.assert_called_once_with(expected_response_text)
        mock_logger.info.assert_any_call(f"Пользователь {mock_message.from_user.id} запросил погоду для города: {city_name}")
        mock_logger.info.assert_any_call(f"Успешно отправлена погода для города {city_name} пользователю {mock_message.from_user.id}.")


@pytest.mark.asyncio
async def test_process_weather_command_no_city():
    """
    Тест: команда /weather вызвана без указания города.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    mock_command = MagicMock(spec=CommandObject, args=None)

    with patch('app.bot.main.logger.info') as mock_logger_info:
        await process_weather_command(mock_message, mock_command)

        mock_message.reply.assert_called_once_with(
            "Пожалуйста, укажите название города после команды /weather.\n"
            "Например: <code>/weather Москва</code>"
        )
        mock_logger_info.assert_called_once_with(f"Команда /weather вызвана без указания города пользователем {mock_message.from_user.id}.")


@pytest.mark.asyncio
async def test_process_weather_command_city_not_found():
    """
    Тест: API погоды вернуло ошибку "город не найден" (404).
    """
    city_name = "НесуществующийГород"
    mock_message = AsyncMock(spec=Message)
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    mock_command = MagicMock(spec=CommandObject, args=city_name)

    mock_weather_api_error_response = {"error": True, "status_code": 404, "message": "city not found"}

    with patch('app.bot.main.get_weather_data', return_value=mock_weather_api_error_response) as mock_get_weather, \
         patch('app.bot.main.logger') as mock_logger:

        await process_weather_command(mock_message, mock_command)

        mock_message.reply.assert_any_call(f"Запрашиваю погоду для города <b>{city_name}</b>...")
        mock_get_weather.assert_called_once_with(city_name.strip())
        mock_message.reply.assert_any_call(f"Город <b>{city_name}</b> не найден. Пожалуйста, проверьте название и попробуйте снова.")
        mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_process_weather_command_api_key_error():
    """
    Тест: API погоды вернуло ошибку "неверный API ключ" (401).
    """
    city_name = "Москва"
    mock_message = AsyncMock(spec=Message)
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    mock_command = MagicMock(spec=CommandObject, args=city_name)

    mock_weather_api_error_response = {"error": True, "status_code": 401, "message": "Invalid API key"}

    with patch('app.bot.main.get_weather_data', return_value=mock_weather_api_error_response) as mock_get_weather, \
         patch('app.bot.main.logger') as mock_logger:

        await process_weather_command(mock_message, mock_command)

        mock_message.reply.assert_any_call(f"Запрашиваю погоду для города <b>{city_name}</b>...")
        mock_get_weather.assert_called_once_with(city_name.strip())
        mock_message.reply.assert_any_call("Проблема с доступом к сервису погоды (неверный API ключ). Администратор уведомлен.")
        mock_logger.critical.assert_called_once()


@pytest.mark.asyncio
async def test_process_weather_command_api_other_error():
    """
    Тест: API погоды вернуло другую ошибку.
    """
    city_name = "Москва"
    mock_message = AsyncMock(spec=Message)
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    mock_command = MagicMock(spec=CommandObject, args=city_name)

    error_message_from_api = "Some other API error"
    mock_weather_api_error_response = {"error": True, "status_code": 500, "message": error_message_from_api}

    with patch('app.bot.main.get_weather_data', return_value=mock_weather_api_error_response) as mock_get_weather, \
         patch('app.bot.main.logger') as mock_logger:

        await process_weather_command(mock_message, mock_command)

        mock_message.reply.assert_any_call(f"Запрашиваю погоду для города <b>{city_name}</b>...")
        mock_get_weather.assert_called_once_with(city_name.strip())
        mock_message.reply.assert_any_call(f"Не удалось получить погоду: {error_message_from_api}")
        mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_process_weather_command_parsing_key_error():
    """
    Тест: ошибка KeyError при парсинге успешного ответа от API.
    """
    city_name = "Москва"
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123, full_name="Tester")
    mock_command = MagicMock(spec=CommandObject, args=city_name)

    malformed_weather_api_response = {
        "weather": [{"description": "ясно"}],
        "wind": {"speed": 3.0, "deg": 180},
        "name": "Москва"
    }

    with patch('app.bot.main.get_weather_data', return_value=malformed_weather_api_response) as mock_get_weather, \
         patch('app.bot.main.logger') as mock_logger:

        await process_weather_command(mock_message, mock_command)

        mock_message.reply.assert_any_call(f"Запрашиваю погоду для города <b>{city_name}</b>...")
        mock_get_weather.assert_called_once_with(city_name.strip())
        mock_message.answer.assert_called_once_with("Не удалось обработать данные о погоде. Попробуйте другой город или повторите попытку позже.")
        mock_logger.error.assert_called_once()
        args, kwargs = mock_logger.error.call_args
        assert "Ошибка парсинга данных о погоде" in args[0]
        assert "отсутствует ключ" in args[0]
        assert "'main'" in args[0] # Проверяем, что указан ключ 'main'

# --- Тесты для process_news_command ---

@pytest.mark.asyncio
async def test_process_news_command_success():
    """
    Тест: успешное получение новостей по команде /news.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)

    mock_articles = [
        {'title': 'Новость 1 <script>alert(1)</script>', 'url': 'http://example.com/1', 'source': {'name': 'Источник 1'}},
        {'title': 'Новость 2', 'url': 'http://example.com/2', 'source': {'name': 'Источник 2'}},
    ]

    with patch('app.bot.main.get_top_headlines', return_value=mock_articles) as mock_get_news, \
         patch('app.bot.main.logger') as mock_logger:

        await process_news_command(mock_message)

        mock_message.reply.assert_called_once_with("Запрашиваю последние главные новости для России...")
        mock_get_news.assert_called_once_with(country="ru", page_size=5)

        expected_lines = ["<b>📰 Последние главные новости (Россия):</b>"]
        # Используем html.escape здесь тоже
        title1_escaped = html.escape("Новость 1 <script>alert(1)</script>") # <-- Исправлено здесь
        expected_lines.append(f"1. <a href='http://example.com/1'>{title1_escaped}</a> (Источник 1)")
        expected_lines.append("2. <a href='http://example.com/2'>Новость 2</a> (Источник 2)")
        expected_text = "\n".join(expected_lines)

        mock_message.answer.assert_called_once_with(expected_text, disable_web_page_preview=True)
        mock_logger.info.assert_any_call(f"Пользователь {mock_message.from_user.id} запросил новости.")
        mock_logger.info.assert_any_call(f"Успешно отправлены новости пользователю {mock_message.from_user.id}.")


@pytest.mark.asyncio
async def test_process_news_command_no_articles():
    """
    Тест: команда /news, API вернул пустой список статей.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)

    mock_articles = []

    with patch('app.bot.main.get_top_headlines', return_value=mock_articles) as mock_get_news, \
         patch('app.bot.main.logger') as mock_logger:

        await process_news_command(mock_message)

        mock_message.reply.assert_any_call("Запрашиваю последние главные новости для России...")
        mock_get_news.assert_called_once_with(country="ru", page_size=5)
        mock_message.reply.assert_any_call("На данный момент нет главных новостей для отображения.")
        mock_logger.info.assert_any_call(f"Главных новостей для России не найдено (пользователь {mock_message.from_user.id}).")


@pytest.mark.asyncio
async def test_process_news_command_api_error():
    """
    Тест: команда /news, API вернул ошибку.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)

    error_message_from_api = "API key invalid"
    mock_api_error_response = {"error": True, "code": "apiKeyInvalid", "message": error_message_from_api, "source": "NewsAPI/HTTP"}

    with patch('app.bot.main.get_top_headlines', return_value=mock_api_error_response) as mock_get_news, \
         patch('app.bot.main.logger') as mock_logger:

        await process_news_command(mock_message)

        mock_message.reply.assert_any_call("Запрашиваю последние главные новости для России...")
        mock_get_news.assert_called_once_with(country="ru", page_size=5)
        mock_message.reply.assert_any_call(f"Не удалось получить новости: {error_message_from_api}")
        mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_process_news_command_unexpected_return():
    """
    Тест: команда /news, API клиент вернул неожиданный результат (не список и не словарь с ошибкой).
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)

    unexpected_response = None

    with patch('app.bot.main.get_top_headlines', return_value=unexpected_response) as mock_get_news, \
         patch('app.bot.main.logger') as mock_logger:

        await process_news_command(mock_message)

        mock_message.reply.assert_any_call("Запрашиваю последние главные новости для России...")
        mock_get_news.assert_called_once_with(country="ru", page_size=5)
        mock_message.reply.assert_any_call("Не удалось получить данные о новостях. Пожалуйста, попробуйте позже.")
        mock_logger.error.assert_called_once()