"""Обработчики для команд, запрашивающих информацию.

Этот модуль содержит хендлеры для команд, которые предоставляют пользователю
информацию по запросу, такую как погода, новости и события. Он также
включает логику для взаимодействия с конечным автоматом (FSM) для
многошаговых сценариев, например, запроса погоды без указания города.
"""
import html
import logging
from typing import Optional

from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext

from app.api_clients.events import get_kudago_events
from app.api_clients.news import get_top_headlines
from app.api_clients.weather import get_weather_data
from app.bot.constants import (
    CMD_EVENTS,
    CMD_NEWS,
    CMD_WEATHER,
    ERROR_MSG_UNKNOWN_API_ERROR,
    KUDAGO_LOCATION_SLUGS,
)
from app.bot.fsm import WeatherStates
from app.database.crud import log_user_action
from app.database.session import get_session

logger = logging.getLogger(__name__)
router = Router()


async def send_weather_for_city(message: types.Message, city_name: str):
    """Запрашивает и отправляет погоду для указанного города.

    Вспомогательная функция, которая инкапсулирует логику запроса к API
    погоды, форматирования и отправки ответа пользователю.

    Args:
        message: Объект сообщения, на который нужно ответить.
        city_name: Название города.
    """
    telegram_id = message.from_user.id
    city_name_clean = city_name.strip()
    log_details = f"город: {city_name_clean}"

    await message.answer(
        f"Запрашиваю погоду для города <b>{html.escape(city_name_clean)}</b>..."
    )

    weather_data = await get_weather_data(city_name_clean)
    log_status_suffix = ""

    with get_session() as db_session:
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
                    directions = [
                        "Северный", "С-В", "Восточный", "Ю-В",
                        "Южный", "Ю-З", "Западный", "С-З",
                    ]
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
            except (KeyError, IndexError) as e:
                logger.error(f"Ошибка парсинга погоды для {city_name_clean}: {e}", exc_info=True)
                await message.answer("Не удалось обработать данные о погоде.")
                log_status_suffix = f", ошибка парсинга: {str(e)[:50]}"
        elif weather_data and weather_data.get("error"):
            error_message = weather_data.get("message", ERROR_MSG_UNKNOWN_API_ERROR)
            status_code = weather_data.get("status_code")
            if status_code == 404:
                await message.answer(f"Город <b>{html.escape(city_name_clean)}</b> не найден.")
            else:
                await message.answer(f"Не удалось получить погоду: {html.escape(error_message)}")
            log_status_suffix = f", ошибка API: {error_message[:50]}"
        else:
            await message.answer("Не удалось получить данные о погоде.")
            log_status_suffix = ", нет данных от API"

        log_user_action(db_session, telegram_id, f"/{CMD_WEATHER}", log_details + log_status_suffix)


@router.message(Command(CMD_WEATHER))
async def process_weather_command(
    message: types.Message, command: CommandObject, state: FSMContext
):
    """Обрабатывает команду /weather.

    Если город указан в аргументах команды, сразу отправляет погоду.
    Если город не указан, переводит пользователя в состояние ожидания
    ввода города.

    Args:
        message: Объект сообщения от пользователя.
        command: Объект, содержащий аргументы команды.
        state: Контекст состояния FSM.
    """
    city_name_arg: Optional[str] = command.args

    if city_name_arg:
        await send_weather_for_city(message, city_name_arg)
    else:
        await message.reply("Пожалуйста, укажите название города.")
        await state.set_state(WeatherStates.waiting_for_city)
        with get_session() as db_session:
            log_user_action(
                db_session, message.from_user.id, f"/{CMD_WEATHER}", "Город не указан, ожидание ввода"
            )


@router.message(StateFilter(WeatherStates.waiting_for_city), F.text)
async def process_city_for_weather(message: types.Message, state: FSMContext):
    """Обрабатывает название города, полученное в состоянии FSM.

    Вызывается, когда пользователь отправляет текстовое сообщение, находясь
    в состоянии `WeatherStates.waiting_for_city`.

    Args:
        message: Объект сообщения от пользователя, содержащий название города.
        state: Контекст состояния FSM.
    """
    await state.clear()
    await send_weather_for_city(message, message.text)


@router.message(Command(CMD_NEWS))
async def process_news_command(message: types.Message):
    """Обрабатывает команду /news.

    Запрашивает последние главные новости из США и отправляет их
    пользователю в виде форматированного списка.

    Args:
        message: Объект сообщения от пользователя.
    """
    telegram_id: int = message.from_user.id
    await message.reply("Запрашиваю последние главные новости для США...")

    with get_session() as db_session:
        articles = await get_top_headlines(page_size=5)
        log_status_details: str

        if isinstance(articles, list) and articles:
            response_lines = ["<b>📰 Последние главные новости (США):</b>"]
            for i, article in enumerate(articles):
                title = html.escape(article.get("title", "Без заголовка"))
                url = article.get("url", "#")
                source = html.escape(article.get("source", {}).get("name", "Неизвестный источник"))
                response_lines.append(f"{i + 1}. <a href='{url}'>{title}</a> ({source})")
            await message.answer("\n".join(response_lines), disable_web_page_preview=True)
            log_status_details = "success, country=us"
        elif isinstance(articles, list):
            await message.reply("На данный момент нет главных новостей для отображения.")
            log_status_details = "no_articles_found, country=us"
        elif isinstance(articles, dict) and articles.get("error"):
            error_message = articles.get("message", ERROR_MSG_UNKNOWN_API_ERROR)
            await message.reply(f"Не удалось получить новости: {html.escape(error_message)}")
            log_status_details = f"api_error: {error_message[:100]}"
        else:
            await message.reply("Не удалось получить данные о новостях.")
            log_status_details = "unexpected_api_response"

        log_user_action(db_session, telegram_id, f"/{CMD_NEWS}", log_status_details)


@router.message(Command(CMD_EVENTS))
async def process_events_command(message: types.Message, command: CommandObject):
    """Обрабатывает команду /events.

    Запрашивает актуальные события для указанного города (через аргумент
    команды) и отправляет их пользователю.

    Args:
        message: Объект сообщения от пользователя.
        command: Объект, содержащий аргументы команды (название города).
    """
    city_arg: Optional[str] = command.args
    telegram_id: int = message.from_user.id

    with get_session() as db_session:
        if not city_arg:
            await message.reply(f"Пожалуйста, укажите город. Например: /{CMD_EVENTS} Москва")
            log_user_action(db_session, telegram_id, f"/{CMD_EVENTS}", "Город не указан")
            return

        city_arg_clean = city_arg.strip()
        location_slug = KUDAGO_LOCATION_SLUGS.get(city_arg_clean.lower())
        log_details = f"город: {city_arg_clean}"
        log_status_suffix = ""

        if not location_slug:
            await message.reply(
                f"К сожалению, не знаю событий для города '{html.escape(city_arg_clean)}'.\n"
                "Попробуйте: Москва, Санкт-Петербург."
            )
            log_status_suffix = ", город не поддерживается"
        else:
            await message.reply(f"Запрашиваю события для города <b>{html.escape(city_arg_clean)}</b>...")
            events_result = await get_kudago_events(location=location_slug, page_size=5)

            if isinstance(events_result, list) and events_result:
                response_lines = [f"<b>🎉 События в городе {html.escape(city_arg_clean.capitalize())}:</b>"]
                for i, event in enumerate(events_result):
                    title = html.escape(event.get("title", "Без заголовка"))
                    site_url = event.get("site_url", "#")
                    response_lines.append(f"{i + 1}. <a href='{site_url}'>{title}</a>")
                await message.answer("\n\n".join(response_lines), disable_web_page_preview=True)
                log_status_suffix = ", успех"
            elif isinstance(events_result, list):
                await message.reply(f"Не найдено событий для города <b>{html.escape(city_arg_clean)}</b>.")
                log_status_suffix = ", не найдено"
            elif isinstance(events_result, dict) and events_result.get("error"):
                error_message = events_result.get("message", ERROR_MSG_UNKNOWN_API_ERROR)
                await message.reply(f"Не удалось получить события: {html.escape(error_message)}")
                log_status_suffix = f", ошибка API: {error_message[:70]}"
            else:
                await message.reply("Не удалось получить данные о событиях.")
                log_status_suffix = ", unexpected_api_response"

        log_user_action(db_session, telegram_id, f"/{CMD_EVENTS}", log_details + log_status_suffix)