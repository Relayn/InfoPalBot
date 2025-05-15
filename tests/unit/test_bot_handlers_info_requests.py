import pytest
import html
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot.main import (
    process_weather_command,
    process_news_command,
    process_events_command
)
from aiogram.types import Message, User as AiogramUser, Chat
from aiogram.filters import CommandObject

# --- Тесты для process_weather_command ---

@pytest.mark.asyncio
async def test_process_weather_command_success():
    city_name = "Москва"
    mock_message = AsyncMock(spec=Message); mock_message.answer = AsyncMock(); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123, full_name="Tester")
    mock_command = MagicMock(spec=CommandObject, args=city_name)
    mock_weather_api_response = {
        "weather": [{"description": "ясно"}],
        "main": {"temp": 20.5, "feels_like": 19.0, "humidity": 50},
        "wind": {"speed": 3.0, "deg": 180}, "name": "Москва"
    }
    with patch('app.bot.main.get_weather_data', return_value=mock_weather_api_response) as mock_get_weather:
        await process_weather_command(mock_message, mock_command)
        mock_message.reply.assert_any_call(f"Запрашиваю погоду для города <b>{html.escape(city_name)}</b>...")
        mock_get_weather.assert_called_once_with(city_name.strip())
        expected_response_text = (
            f"<b>Погода в городе {html.escape(mock_weather_api_response.get('name', city_name))}:</b>\n"
            f"🌡️ Температура: {mock_weather_api_response['main']['temp']}°C (ощущается как {mock_weather_api_response['main']['feels_like']}°C)\n"
            f"💧 Влажность: {mock_weather_api_response['main']['humidity']}%\n"
            f"💨 Ветер: {mock_weather_api_response['wind']['speed']} м/с, Южный\n"
            f"☀️ Описание: Ясно"
        )
        mock_message.answer.assert_called_once_with(expected_response_text)

@pytest.mark.asyncio
async def test_process_weather_command_no_city():
    mock_message = AsyncMock(spec=Message); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    mock_command = MagicMock(spec=CommandObject, args=None)
    await process_weather_command(mock_message, mock_command)
    # Используем текст из актуального кода бота
    mock_message.reply.assert_called_once_with("Пожалуйста, укажите название города...")


@pytest.mark.asyncio
async def test_process_weather_command_city_not_found():
    city_name = "НесуществующийГород"
    mock_message = AsyncMock(spec=Message); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    mock_command = MagicMock(spec=CommandObject, args=city_name)
    mock_weather_api_error_response = {"error": True, "status_code": 404, "message": "city not found"}
    with patch('app.bot.main.get_weather_data', return_value=mock_weather_api_error_response):
        await process_weather_command(mock_message, mock_command)
        # Проверяем оба вызова reply
        mock_message.reply.assert_any_call(f"Запрашиваю погоду для города <b>{html.escape(city_name)}</b>...")
        mock_message.reply.assert_any_call(f"Не удалось получить погоду: {html.escape(mock_weather_api_error_response.get('message', 'Ошибка'))}")


@pytest.mark.asyncio
async def test_process_weather_command_api_key_error():
    city_name = "Москва"
    mock_message = AsyncMock(spec=Message); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    mock_command = MagicMock(spec=CommandObject, args=city_name)
    mock_weather_api_error_response = {"error": True, "status_code": 401, "message": "Invalid API key"}
    with patch('app.bot.main.get_weather_data', return_value=mock_weather_api_error_response):
        await process_weather_command(mock_message, mock_command)
        mock_message.reply.assert_any_call(f"Запрашиваю погоду для города <b>{html.escape(city_name)}</b>...")
        mock_message.reply.assert_any_call(f"Не удалось получить погоду: {html.escape(mock_weather_api_error_response.get('message', 'Ошибка'))}")


@pytest.mark.asyncio
async def test_process_weather_command_api_other_error():
    city_name = "Москва"
    mock_message = AsyncMock(spec=Message); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    mock_command = MagicMock(spec=CommandObject, args=city_name)
    error_message_from_api = "Some other API error"
    mock_weather_api_error_response = {"error": True, "status_code": 500, "message": error_message_from_api}
    with patch('app.bot.main.get_weather_data', return_value=mock_weather_api_error_response):
        await process_weather_command(mock_message, mock_command)
        mock_message.reply.assert_any_call(f"Запрашиваю погоду для города <b>{html.escape(city_name)}</b>...")
        mock_message.reply.assert_any_call(f"Не удалось получить погоду: {html.escape(error_message_from_api)}")

@pytest.mark.asyncio
async def test_process_weather_command_parsing_key_error():
    city_name = "Москва"
    mock_message = AsyncMock(spec=Message); mock_message.answer = AsyncMock(); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123, full_name="Tester")
    mock_command = MagicMock(spec=CommandObject, args=city_name)
    malformed_weather_api_response = {"weather": [{"description": "ясно"}], "wind": {"speed": 3.0, "deg": 180}, "name": "Москва"}
    with patch('app.bot.main.get_weather_data', return_value=malformed_weather_api_response):
        await process_weather_command(mock_message, mock_command)
        mock_message.reply.assert_any_call(f"Запрашиваю погоду для города <b>{html.escape(city_name)}</b>...")
        mock_message.answer.assert_called_once_with("Не удалось обработать данные о погоде...")


# --- Тесты для process_news_command ---
@pytest.mark.asyncio
async def test_process_news_command_success():
    mock_message = AsyncMock(spec=Message); mock_message.answer = AsyncMock(); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    mock_articles = [
        {'title': 'Новость 1 <script>alert(1)</script>', 'url': 'http://example.com/1', 'source': {'name': 'Источник 1'}},
        {'title': 'Новость 2', 'url': 'http://example.com/2', 'source': {'name': 'Источник 2'}},
    ]
    with patch('app.bot.main.get_top_headlines', return_value=mock_articles):
        await process_news_command(mock_message)
        mock_message.reply.assert_called_once_with("Запрашиваю последние главные новости для России...")
        expected_lines = ["<b>📰 Последние главные новости (Россия):</b>"]
        title1_escaped = html.escape("Новость 1 <script>alert(1)</script>")
        expected_lines.append(f"1. <a href='http://example.com/1'>{title1_escaped}</a> (Источник 1)")
        expected_lines.append("2. <a href='http://example.com/2'>Новость 2</a> (Источник 2)")
        expected_text = "\n".join(expected_lines)
        mock_message.answer.assert_called_once_with(expected_text, disable_web_page_preview=True)

@pytest.mark.asyncio
async def test_process_news_command_no_articles():
    mock_message = AsyncMock(spec=Message); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    with patch('app.bot.main.get_top_headlines', return_value=[]):
        await process_news_command(mock_message)
        mock_message.reply.assert_any_call("Запрашиваю последние главные новости для России...")
        mock_message.reply.assert_any_call("На данный момент нет главных новостей...")


@pytest.mark.asyncio
async def test_process_news_command_api_error():
    mock_message = AsyncMock(spec=Message); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    error_message_from_api = "API key invalid"
    mock_api_error_response = {"error": True, "code": "apiKeyInvalid", "message": error_message_from_api, "source": "NewsAPI/HTTP"}
    with patch('app.bot.main.get_top_headlines', return_value=mock_api_error_response):
        await process_news_command(mock_message)
        mock_message.reply.assert_any_call("Запрашиваю последние главные новости для России...")
        mock_message.reply.assert_any_call(f"Не удалось получить новости: {html.escape(error_message_from_api)}")

@pytest.mark.asyncio
async def test_process_news_command_unexpected_return():
    mock_message = AsyncMock(spec=Message); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    with patch('app.bot.main.get_top_headlines', return_value=None):
        await process_news_command(mock_message)
        mock_message.reply.assert_any_call("Запрашиваю последние главные новости для России...")
        mock_message.reply.assert_any_call("Не удалось получить данные о новостях...")


# --- Тесты для process_events_command ---
@pytest.mark.asyncio
async def test_process_events_command_success():
    city_arg = "Москва"; location_slug = "msk"
    mock_message = AsyncMock(spec=Message); mock_message.answer = AsyncMock(); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=456)
    mock_command = MagicMock(spec=CommandObject, args=city_arg)
    mock_events = [
        {'id': 1, 'title': 'Событие 1 <Тест HTML>', 'description': 'Описание 1 <p>с тегом</p>', 'site_url': 'http://site.com/1'},
        {'id': 2, 'title': 'Событие 2', 'description': 'Описание 2', 'site_url': 'http://site.com/2'},
    ]
    with patch('app.bot.main.get_kudago_events', return_value=mock_events):
        await process_events_command(mock_message, mock_command)
        mock_message.reply.assert_any_call(f"Запрашиваю актуальные события для города <b>{html.escape(city_arg)}</b>...")
        expected_lines = [f"<b>🎉 Актуальные события в городе {html.escape(city_arg.capitalize())}:</b>"]
        title1_escaped = html.escape('Событие 1 <Тест HTML>')
        desc1_escaped = html.escape("Описание 1 с тегом".strip())
        expected_lines.append(f"1. <a href='http://site.com/1'>{title1_escaped}</a>\n   <i>{desc1_escaped}</i>")
        title2_escaped = html.escape('Событие 2')
        desc2_escaped = html.escape("Описание 2".strip())
        expected_lines.append(f"2. <a href='http://site.com/2'>{title2_escaped}</a>\n   <i>{desc2_escaped}</i>")
        expected_text = "\n\n".join(expected_lines)
        mock_message.answer.assert_called_once_with(expected_text, disable_web_page_preview=True)

@pytest.mark.asyncio
async def test_process_events_command_no_city_arg():
    mock_message = AsyncMock(spec=Message); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=456)
    mock_command = MagicMock(spec=CommandObject, args=None)
    await process_events_command(mock_message, mock_command)
    mock_message.reply.assert_called_once_with("Пожалуйста, укажите город...\nДоступные города: Москва, Санкт-Петербург...")


@pytest.mark.asyncio
async def test_process_events_command_unknown_city():
    city_arg = "Неизвестный Город"
    mock_message = AsyncMock(spec=Message); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=456)
    mock_command = MagicMock(spec=CommandObject, args=city_arg)
    await process_events_command(mock_message, mock_command)
    mock_message.reply.assert_called_once_with(f"К сожалению, не знаю событий для города '{html.escape(city_arg)}'...\nПопробуйте: Москва, Санкт-Петербург...")

@pytest.mark.asyncio
async def test_process_events_command_no_events_found():
    city_arg = "спб"; location_slug = "spb"
    mock_message = AsyncMock(spec=Message); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=456)
    mock_command = MagicMock(spec=CommandObject, args=city_arg)
    with patch('app.bot.main.get_kudago_events', return_value=[]):
        await process_events_command(mock_message, mock_command)
        mock_message.reply.assert_any_call(f"Запрашиваю актуальные события для города <b>{html.escape(city_arg)}</b>...")
        mock_message.reply.assert_any_call(f"Не найдено актуальных событий для города <b>{html.escape(city_arg)}</b>.")

@pytest.mark.asyncio
async def test_process_events_command_api_error():
    city_arg = "Екатеринбург"; location_slug = "ekb"
    mock_message = AsyncMock(spec=Message); mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=456)
    mock_command = MagicMock(spec=CommandObject, args=city_arg)
    error_message_from_api = "Some API error"
    mock_api_error_response = {"error": True, "message": error_message_from_api, "source": "KudaGo HTTP"}
    with patch('app.bot.main.get_kudago_events', return_value=mock_api_error_response):
        await process_events_command(mock_message, mock_command)
        mock_message.reply.assert_any_call(f"Запрашиваю актуальные события для города <b>{html.escape(city_arg)}</b>...")
        mock_message.reply.assert_any_call(f"Не удалось получить события: {html.escape(error_message_from_api)}")