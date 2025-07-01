import logging
import html
from typing import Optional

from aiogram import Router, types
from aiogram.filters import Command, CommandObject

from app.api_clients.events import get_kudago_events
from app.api_clients.news import get_top_headlines
from app.api_clients.weather import get_weather_data
from app.database.crud import log_user_action
from app.database.session import get_session
from ..constants import KUDAGO_LOCATION_SLUGS

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("weather"))
async def process_weather_command(message: types.Message, command: CommandObject):
    # ... (код без изменений) ...
    city_name_arg: Optional[str] = command.args
    telegram_id: int = message.from_user.id
    log_command: str = "/weather"

    with get_session() as db_session:
        if not city_name_arg:
            await message.reply("Пожалуйста, укажите название города...")
            log_user_action(db_session, telegram_id, log_command, "Город не указан")
            return

        city_name_clean: str = city_name_arg.strip()
        log_details = f"город: {city_name_clean}"
        await message.reply(
            f"Запрашиваю погоду для города <b>{html.escape(city_name_clean)}</b>..."
        )

        weather_data = await get_weather_data(city_name_clean)
        log_status_suffix = ""

        if weather_data and not weather_data.get("error"):
            try:
                description = weather_data["weather"][0]["description"].capitalize()
                temp = weather_data["main"]["temp"]
                feels_like = weather_data["main"]["feels_like"]
                humidity = weather_data["main"]["humidity"]
                wind_speed = weather_data["wind"]["speed"]
                wind_deg = weather_data["wind"].get("deg")
                wind_direction_str = ""
                if wind_deg is not None:
                    directions = ["Северный", "С-В", "Восточный", "Ю-В", "Южный", "Ю-З", "Западный", "С-З"]
                    wind_direction_str = f", {directions[int((wind_deg % 360) / 45)]}"

                response_text = (
                    f"<b>Погода в городе {html.escape(weather_data.get('name', city_name_clean))}:</b>\n"
                    f"🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n"
                    f"💧 Влажность: {humidity}%\n"
                    f"💨 Ветер: {wind_speed} м/с{wind_direction_str}\n"
                    f"☀️ Описание: {description}"
                )
                await message.answer(response_text)
                log_status_suffix = ", успех"
            except KeyError as e:
                logger.error(f"Ошибка парсинга данных о погоде для {city_name_clean}: ключ {e}", exc_info=True)
                await message.answer("Не удалось обработать данные о погоде...")
                log_status_suffix = f", ошибка парсинга: {str(e)[:50]}"
        elif weather_data and weather_data.get("error"):
            error_message = weather_data.get("message", "Неизвестная ошибка API.")
            status_code = weather_data.get("status_code")
            if status_code == 404:
                await message.reply(f"Город <b>{html.escape(city_name_clean)}</b> не найден...")
            elif status_code == 401:
                await message.reply("Проблема с доступом к сервису погоды...")
            else:
                await message.reply(f"Не удалось получить погоду: {html.escape(error_message)}")
            log_status_suffix = f", ошибка API: {error_message[:50]}"
        else:
            await message.reply("Не удалось получить данные о погоде...")
            log_status_suffix = ", нет данных от API"

        log_user_action(db_session, telegram_id, log_command, log_details + log_status_suffix)


@router.message(Command("news"))
async def process_news_command(message: types.Message):
    """
    Обрабатывает команду /news.
    """
    telegram_id: int = message.from_user.id
    await message.reply("Запрашиваю последние главные новости для США...")

    with get_session() as db_session:
        # Вызываем без аргументов, будет использовано значение по умолчанию "us"
        articles = await get_top_headlines(page_size=5)
        log_status_details = "unknown_error"

        if isinstance(articles, list) and articles:
            response_lines = ["<b>📰 Последние главные новости (США):</b>"]
            for i, article in enumerate(articles):
                title = html.escape(article.get("title", "Без заголовка"))
                url = article.get("url", "#")
                source = html.escape(article.get("source", {}).get("name", "Неизвестный источник"))
                response_lines.append(f"{i + 1}. <a href='{url}'>{title}</a> ({source})")
            await message.answer("\n".join(response_lines), disable_web_page_preview=True)
            log_status_details = "success, country=us"
        elif isinstance(articles, list) and not articles:
            await message.reply("На данный момент нет главных новостей для отображения.")
            log_status_details = "no_articles_found, country=us"
        elif isinstance(articles, dict) and articles.get("error"):
            error_message = articles.get("message", "Неизвестная ошибка API.")
            await message.reply(f"Не удалось получить новости: {html.escape(error_message)}")
            log_status_details = f"api_error: {error_message[:100]}"
        else:
            await message.reply("Не удалось получить данные о новостях...")
            log_status_details = "unexpected_api_response"

        log_user_action(db_session, telegram_id, "/news", log_status_details)


@router.message(Command("events"))
async def process_events_command(message: types.Message, command: CommandObject):
    # ... (код без изменений) ...
    city_arg: Optional[str] = command.args
    telegram_id: int = message.from_user.id

    with get_session() as db_session:
        if not city_arg:
            await message.reply("Пожалуйста, укажите город...\nДоступные города: Москва, Санкт-Петербург...")
            log_user_action(db_session, telegram_id, "/events", "Город не указан")
            return

        city_arg_clean = city_arg.strip()
        location_slug = KUDAGO_LOCATION_SLUGS.get(city_arg_clean.lower())
        log_details = f"город: {city_arg_clean}"

        if not location_slug:
            await message.reply(f"К сожалению, не знаю событий для города '{html.escape(city_arg_clean)}'...\nПопробуйте: Москва, Санкт-Петербург...")
            log_details += ", город не поддерживается"
            log_user_action(db_session, telegram_id, "/events", log_details)
            return

        await message.reply(f"Запрашиваю актуальные события для города <b>{html.escape(city_arg_clean)}</b>...")
        events_result = await get_kudago_events(location=location_slug, page_size=5)
        log_status_suffix = ""

        if isinstance(events_result, list) and events_result:
            response_lines = [f"<b>🎉 Актуальные события в городе {html.escape(city_arg_clean.capitalize())}:</b>"]
            for i, event in enumerate(events_result):
                title = html.escape(event.get("title", "Без заголовка"))
                site_url = event.get("site_url", "#")
                description_raw = event.get("description", "")
                description = html.unescape(description_raw.replace("<p>", "").replace("</p>", "").replace("<br>", "\n")).strip()
                event_str = f"{i + 1}. <a href='{site_url}'>{title}</a>"
                if description:
                    event_str += f"\n   <i>{html.escape(description[:100])}{'...' if len(description) > 100 else ''}</i>"
                response_lines.append(event_str)
            await message.answer("\n\n".join(response_lines), disable_web_page_preview=True)
            log_status_suffix = ", успех"
        elif isinstance(events_result, list) and not events_result:
            await message.reply(f"Не найдено актуальных событий для города <b>{html.escape(city_arg_clean)}</b>.")
            log_status_suffix = ", не найдено"
        elif isinstance(events_result, dict) and events_result.get("error"):
            error_message = events_result.get("message", "Неизвестная ошибка API.")
            await message.reply(f"Не удалось получить события: {html.escape(error_message)}")
            log_status_suffix = f", ошибка API: {error_message[:70]}"
        else:
            await message.reply("Не удалось получить данные о событиях...")
            log_status_suffix = ", unexpected_api_response"

        log_user_action(db_session, telegram_id, "/events", log_details + log_status_suffix)