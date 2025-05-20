import logging
import asyncio
import html
from typing import Optional # <-- Добавлен импорт Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from sqlmodel import Session # <-- Добавлен импорт Session для type hinting в log_user_action

from app.config import settings
from app.database.session import get_session, create_db_and_tables
from app.database.crud import (
    create_user_if_not_exists,
    get_user_by_telegram_id,
    create_subscription,
    get_subscriptions_by_user_id,
    get_subscription_by_user_and_type,
    delete_subscription,
    create_log_entry
)
from app.database.models import User, Subscription # Убедимся, что User и Subscription импортированы
from app.api_clients.weather import get_weather_data
from app.api_clients.news import get_top_headlines
from app.api_clients.events import get_kudago_events
from .constants import INFO_TYPE_WEATHER, INFO_TYPE_NEWS, INFO_TYPE_EVENTS, KUDAGO_LOCATION_SLUGS
from app.scheduler.main import schedule_jobs, shutdown_scheduler, set_bot_instance, scheduler as aps_scheduler

logging.basicConfig(level=settings.LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

default_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=default_properties)
dp = Dispatcher()

KUDAGO_LOCATION_SLUGS = { # Оставляем здесь, т.к. используется только в этом файле (или переносим в constants.py вместе с INFO_TYPE)
    "москва": "msk", "мск": "msk", "moscow": "msk",
    "санкт-петербург": "spb", "спб": "spb", "питер": "spb", "saint petersburg": "spb",
    "новосибирск": "nsk", "нск": "nsk",
    "екатеринбург": "ekb", "екб": "ekb",
    "казань": "kzn",
    "нижний новгород": "nnv",
}

class SubscriptionStates(StatesGroup):
    choosing_info_type = State()
    entering_city_weather = State()
    entering_city_events = State()

# Вспомогательная функция для логирования действия пользователя
def log_user_action(db_session: Session, telegram_id: int, command: str, details: Optional[str] = None):
    """Логирует действие пользователя в базу данных."""
    # logger.debug(f"Logging action for telegram_id {telegram_id}: command='{command}', details='{details}'") # Для отладки самой функции лога
    user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
    user_db_id = user.id if user else None
    try:
        create_log_entry(session=db_session, user_id=user_db_id, command=command, details=details)
    except Exception as e:
        logger.error(f"Failed to create log entry for user {telegram_id}, command {command}: {e}", exc_info=True)


@dp.message(Command('cancel'), StateFilter('*'))
async def cmd_cancel_any_state(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    current_state_str = await state.get_state()
    log_details = f"State before cancel: {current_state_str}"

    with next(get_session()) as db_session:
        log_user_action(db_session, telegram_id, "/cancel", log_details)

    if current_state_str is None:
        await message.answer("Нет активного действия для отмены.", reply_markup=ReplyKeyboardRemove())
        return

    logger.info(f"Пользователь {telegram_id} отменил действие командой /cancel из состояния {current_state_str}.")
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=ReplyKeyboardRemove())


@dp.message(Command('start'), StateFilter('*'))
async def process_start_command(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    logger.info(f"Команда /start вызвана пользователем {telegram_id}. Текущее состояние: {await state.get_state()}")
    await state.clear()

    db_user_internal_id: Optional[int] = None
    try:
        with next(get_session()) as db_session:
            db_user = create_user_if_not_exists(session=db_session, telegram_id=telegram_id)
            db_user_internal_id = db_user.id
            logger.info(f"Обработана команда /start от пользователя {telegram_id}. Пользователь в БД: {db_user_internal_id}")
            log_user_action(db_session, telegram_id, "/start") # Используем вспомогательную функцию

        await message.answer(
            f"Привет, {message.from_user.full_name}! Я InfoPalBot. Я могу предоставить тебе актуальную информацию.\n"
            f"Используй /help, чтобы увидеть список доступных команд.")
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /start для пользователя {telegram_id}: {e}", exc_info=True)
        if db_user_internal_id: # Если ID пользователя известен, логируем с ним
             with next(get_session()) as db_session_err:
                log_user_action(db_session_err, telegram_id, "/start_error", str(e)[:250])
        else: # Если ID пользователя не известен (ошибка до создания/получения)
            with next(get_session()) as db_session_err:
                log_user_action(db_session_err, telegram_id, "/start_error", f"User ID unknown, error: {str(e)[:200]}")
        await message.answer("Произошла ошибка при обработке вашего запроса. Попробуйте позже.")

@dp.message(Command('help'))
async def process_help_command(message: types.Message):
    telegram_id = message.from_user.id
    help_text = (
        "<b>Доступные команды:</b>\n"
        "<code>/start</code> - Начать работу с ботом и зарегистрироваться\n"
        "<code>/help</code> - Показать это сообщение со справкой\n"
        "<code>/weather [город]</code> - Получить текущий прогноз погоды (например, <code>/weather Москва</code>)\n"
        "<code>/news</code> - Получить последние новости (Россия)\n"
        "<code>/events [город]</code> - Узнать о предстоящих событиях (например, <code>/events спб</code>). Доступные города см. в /events без аргумента.\n"
        "<code>/subscribe</code> - Подписаться на рассылку\n"
        "<code>/mysubscriptions</code> - Посмотреть ваши активные подписки\n"
        "<code>/unsubscribe</code> - Отписаться от рассылки\n"
        "<code>/cancel</code> - Отменить текущее действие (например, подписку)\n"
    )
    await message.answer(help_text)
    logger.info(f"Отправлена справка по команде /help пользователю {telegram_id}")
    with next(get_session()) as db_session:
        log_user_action(db_session, telegram_id, "/help")

# Этот код является продолжением предыдущей части app/bot/main.py
# ... (код до process_help_command включительно, как в Части 1) ...
@dp.message(Command('weather'))
async def process_weather_command(message: types.Message, command: CommandObject):
    city_name_arg = command.args
    telegram_id = message.from_user.id
    log_details = "N/A"  # Значение по умолчанию

    try:
        with next(get_session()) as db_session:
            if not city_name_arg:
                await message.reply("Пожалуйста, укажите название города...")
                logger.info(f"Команда /weather вызвана без указания города пользователем {telegram_id}.")
                log_details = "Город не указан"
                log_user_action(db_session, telegram_id, "/weather", log_details)
                return

            city_name_clean = city_name_arg.strip()
            log_details = f"город: {city_name_clean}"
            logger.info(f"Пользователь {telegram_id} запросил погоду для города: {city_name_clean}")
            await message.reply(f"Запрашиваю погоду для города <b>{html.escape(city_name_clean)}</b>...")

            weather_data = await get_weather_data(city_name_clean)
            log_status_suffix = ""  # Для добавления к log_details

            if weather_data and not weather_data.get("error"):
                try:
                    description = weather_data['weather'][0]['description'].capitalize();
                    temp = weather_data['main']['temp']
                    feels_like = weather_data['main']['feels_like'];
                    humidity = weather_data['main']['humidity']
                    wind_speed = weather_data['wind']['speed'];
                    wind_deg = weather_data['wind'].get('deg')
                    wind_direction_str = ""
                    if wind_deg is not None:
                        directions = ["Северный", "С-В", "Восточный", "Ю-В", "Южный", "Ю-З", "Западный", "С-З"]
                        wind_direction_str = f", {directions[int((wind_deg % 360) / 45)]}"
                    response_text = (
                        f"<b>Погода в городе {html.escape(weather_data.get('name', city_name_clean))}:</b>\n"
                        f"🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n💧 Влажность: {humidity}%\n"
                        f"💨 Ветер: {wind_speed} м/с{wind_direction_str}\n☀️ Описание: {description}"
                    )
                    await message.answer(response_text)
                    log_status_suffix = ", успех"
                except KeyError as e:
                    logger.error(
                        f"Ошибка парсинга данных о погоде для {city_name_clean}: ключ {e}. Данные: {weather_data}",
                        exc_info=True)
                    await message.answer("Не удалось обработать данные о погоде...")
                    log_status_suffix = f", ошибка парсинга: {str(e)[:50]}"
                except Exception as e:
                    logger.error(f"Непредвиденная ошибка при формировании ответа о погоде для {city_name_clean}: {e}",
                                 exc_info=True)
                    await message.answer("Произошла ошибка при отображении погоды.")
                    log_status_suffix = f", ошибка отображения: {str(e)[:50]}"

            elif weather_data and weather_data.get("error"):
                error_message_text = weather_data.get("message", "Неизвестная ошибка API.")
                status_code = weather_data.get("status_code")
                if status_code == 404:
                    await message.reply(f"Город <b>{html.escape(city_name_clean)}</b> не найден...")
                elif status_code == 401:
                    await message.reply("Проблема с доступом к сервису погоды...")
                    logger.critical("API ключ OpenWeatherMap недействителен!")
                else:
                    await message.reply(f"Не удалось получить погоду: {html.escape(error_message_text)}")
                logger.warning(f"Ошибка API погоды для {city_name_clean} (user {telegram_id}): {error_message_text}")
                log_status_suffix = f", ошибка API: {error_message_text[:50]}"
            else:
                await message.reply("Не удалось получить данные о погоде...")
                logger.error(
                    f"get_weather_data вернул None/неожиданный ответ для {city_name_clean} (user {telegram_id}).")
                log_status_suffix = ", нет данных от API"

            log_user_action(db_session, telegram_id, "/weather", log_details + log_status_suffix)

    except Exception as e:
        logger.error(f"Критическая ошибка в process_weather_command для {telegram_id}, город {city_name_arg}: {e}",
                     exc_info=True)
        await message.answer("Произошла внутренняя ошибка сервера...")
        try:
            with next(get_session()) as db_session_err:
                log_user_action(db_session_err, telegram_id, "/weather_critical_error", str(e)[:250])
        except Exception as log_e:
            logger.error(f"Не удалось залогировать критическую ошибку /weather: {log_e}")


@dp.message(Command('news'))
async def process_news_command(message: types.Message):
    telegram_id = message.from_user.id
    logger.info(f"Пользователь {telegram_id} запросил новости.")
    await message.reply("Запрашиваю последние главные новости для России...")

    log_status_details = "unknown_error"
    try:
        with next(get_session()) as db_session:
            articles_or_error = await get_top_headlines(country="ru", page_size=5)

            if isinstance(articles_or_error, list) and articles_or_error:
                response_lines = ["<b>📰 Последние главные новости (Россия):</b>"]
                for i, article in enumerate(articles_or_error):
                    title = html.escape(article.get('title', 'Без заголовка'));
                    url = article.get('url', '#')
                    source = html.escape(article.get('source', {}).get('name', 'Неизвестный источник'))
                    response_lines.append(f"{i + 1}. <a href='{url}'>{title}</a> ({source})")
                await message.answer("\n".join(response_lines), disable_web_page_preview=True)
                logger.info(f"Успешно отправлены новости пользователю {telegram_id}.")
                log_status_details = "success"
            elif isinstance(articles_or_error, list) and not articles_or_error:
                await message.reply("На данный момент нет главных новостей для отображения.")
                logger.info(f"Главных новостей для России не найдено (пользователь {telegram_id}).")
                log_status_details = "no_articles_found"
            elif isinstance(articles_or_error, dict) and articles_or_error.get("error"):
                error_message_text = articles_or_error.get("message", "Неизвестная ошибка API.")
                await message.reply(f"Не удалось получить новости: {html.escape(error_message_text)}")
                logger.warning(f"Ошибка API новостей (user {telegram_id}): {error_message_text}")
                log_status_details = f"api_error: {error_message_text[:100]}"
            else:
                await message.reply("Не удалось получить данные о новостях...")
                logger.error(
                    f"get_top_headlines вернул неожиданный ответ для России (user {telegram_id}): {articles_or_error}")
                log_status_details = "unexpected_api_response"

            log_user_action(db_session, telegram_id, "/news", log_status_details)

    except Exception as e:
        logger.error(f"Критическая ошибка в process_news_command для {telegram_id}: {e}", exc_info=True)
        await message.answer("Произошла внутренняя ошибка сервера...")
        try:
            with next(get_session()) as db_session_err:
                log_user_action(db_session_err, telegram_id, "/news_critical_error", str(e)[:250])
        except Exception as log_e:
            logger.error(f"Не удалось залогировать критическую ошибку /news: {log_e}")


# Этот код является продолжением Части 2 файла app/bot/main.py

# ... (код до process_news_command включительно, как в Части 2) ...

@dp.message(Command('events'))
async def process_events_command(message: types.Message, command: CommandObject):
    city_arg = command.args
    telegram_id = message.from_user.id
    log_details = "N/A"
    db_user_internal_id: Optional[int] = None

    try:
        with next(get_session()) as db_session:
            db_user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
            if db_user:
                db_user_internal_id = db_user.id

            if not city_arg:
                await message.reply("Пожалуйста, укажите город...\nДоступные города: Москва, Санкт-Петербург...")
                logger.info(f"Команда /events вызвана без указания города пользователем {telegram_id}.")
                log_details = "Город не указан"
                log_user_action(db_session, telegram_id, "/events", log_details)
                return

            city_arg_clean = city_arg.strip()
            city_name_lower = city_arg_clean.lower()
            location_slug = KUDAGO_LOCATION_SLUGS.get(city_name_lower)
            log_details = f"город: {city_arg_clean}"

            if not location_slug:
                await message.reply(
                    f"К сожалению, не знаю событий для города '{html.escape(city_arg_clean)}'...\nПопробуйте: Москва, Санкт-Петербург...")
                logger.info(
                    f"Пользователь {telegram_id} запросил события для неподдерживаемого города: {city_arg_clean}")
                log_details += ", город не поддерживается"
                log_user_action(db_session, telegram_id, "/events", log_details)
                return

            logger.info(
                f"Пользователь {telegram_id} запросил события KudaGo для города: {city_arg_clean} (slug: {location_slug})")
            await message.reply(f"Запрашиваю актуальные события для города <b>{html.escape(city_arg_clean)}</b>...")

            events_result = await get_kudago_events(location=location_slug, page_size=5)
            log_status_suffix = ""

            if isinstance(events_result, list) and events_result:
                response_lines = [f"<b>🎉 Актуальные события в городе {html.escape(city_arg_clean.capitalize())}:</b>"]
                for i, event in enumerate(events_result):
                    title = html.escape(event.get('title', 'Без заголовка'));
                    site_url = event.get('site_url', '#')
                    description_raw = event.get('description', '');
                    description = html.unescape(
                        description_raw.replace('<p>', '').replace('</p>', '').replace('<br>', '\n')).strip()
                    event_str = f"{i + 1}. <a href='{site_url}'>{title}</a>"
                    if description:
                        max_desc_len = 100
                        if len(description) > max_desc_len: description = description[:max_desc_len] + "..."
                        event_str += f"\n   <i>{html.escape(description)}</i>"
                    response_lines.append(event_str)
                await message.answer("\n\n".join(response_lines), disable_web_page_preview=True)
                logger.info(f"Успешно отправлены события KudaGo для {location_slug} пользователю {telegram_id}.")
                log_status_suffix = ", успех"
            elif isinstance(events_result, list) and not events_result:
                await message.reply(f"Не найдено актуальных событий для города <b>{html.escape(city_arg_clean)}</b>.")
                logger.info(f"Актуальных событий KudaGo для {location_slug} не найдено (пользователь {telegram_id}).")
                log_status_suffix = ", не найдено"
            elif isinstance(events_result, dict) and events_result.get("error"):
                error_message_text = events_result.get("message", "Неизвестная ошибка API.")
                await message.reply(f"Не удалось получить события: {html.escape(error_message_text)}")
                logger.warning(
                    f"Ошибка API событий KudaGo для {location_slug} (user {telegram_id}): {error_message_text}")
                log_status_suffix = f", ошибка API: {error_message_text[:70]}"
            else:
                await message.reply("Не удалось получить данные о событиях...")
                logger.error(
                    f"get_kudago_events вернул неожиданный ответ для {location_slug} (user {telegram_id}): {events_result}")
                log_status_suffix = ", unexpected_api_response"

            log_user_action(db_session, telegram_id, "/events", log_details + log_status_suffix)

    except Exception as e:
        logger.error(f"Критическая ошибка в process_events_command для {telegram_id}, город {city_arg}: {e}",
                     exc_info=True)
        await message.answer("Произошла внутренняя ошибка сервера...")
        try:
            with next(get_session()) as db_session_err:
                log_user_action(db_session_err, telegram_id, "/events_critical_error", str(e)[:250])
        except Exception as log_e:
            logger.error(f"Не удалось залогировать критическую ошибку /events: {log_e}")


# --- Обработчики для /subscribe и FSM ---

@dp.message(Command('subscribe'), StateFilter(None))
async def process_subscribe_command_start(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    with next(get_session()) as db_session:
        log_user_action(db_session, telegram_id, "/subscribe", "Start subscription process")
    logger.info(f"Пользователь {telegram_id} начал процесс подписки командой /subscribe.")
    keyboard_buttons = [
        [InlineKeyboardButton(text="🌦️ Погода", callback_data=f"subscribe_type:{INFO_TYPE_WEATHER}")],
        [InlineKeyboardButton(text="📰 Новости (Россия)", callback_data=f"subscribe_type:{INFO_TYPE_NEWS}")],
        [InlineKeyboardButton(text="🎉 События", callback_data=f"subscribe_type:{INFO_TYPE_EVENTS}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="subscribe_fsm_cancel")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer("На какой тип информации вы хотите подписаться?", reply_markup=keyboard)
    await state.set_state(SubscriptionStates.choosing_info_type)


@dp.callback_query(StateFilter(SubscriptionStates.choosing_info_type), F.data.startswith("subscribe_type:"))
async def process_info_type_choice(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    selected_type = callback_query.data.split(":")[1];
    telegram_id = callback_query.from_user.id
    log_details = f"Type chosen: {selected_type}"

    await state.update_data(info_type=selected_type)

    if selected_type == INFO_TYPE_WEATHER:
        await callback_query.message.edit_text("Вы выбрали 'Погода'.\nПожалуйста, введите название города...")
        await state.set_state(SubscriptionStates.entering_city_weather)
    elif selected_type == INFO_TYPE_EVENTS:
        await callback_query.message.edit_text(
            "Вы выбрали 'События'.\nПожалуйста, введите название города (например, Москва, спб).")
        await state.set_state(SubscriptionStates.entering_city_events)
    elif selected_type == INFO_TYPE_NEWS:
        frequency = "daily"
        with next(get_session()) as db_session:
            log_user_action(db_session, telegram_id, "subscribe_type_selected",
                            log_details)  # Логируем выбор перед действием
            db_user = create_user_if_not_exists(db_session, telegram_id)
            existing_subscription = get_subscription_by_user_and_type(db_session, db_user.id, INFO_TYPE_NEWS)
            if existing_subscription:
                await callback_query.message.edit_text("Вы уже подписаны на 'Новости (Россия)'.")
                log_user_action(db_session, telegram_id, "subscribe_attempt_duplicate", log_details)
            else:
                create_subscription(db_session, db_user.id, INFO_TYPE_NEWS, frequency)
                log_user_action(db_session, telegram_id, "subscribe_confirm",
                                f"Type: {INFO_TYPE_NEWS}, Freq: {frequency}")
                await callback_query.message.edit_text(
                    f"Вы успешно подписались на 'Новости (Россия)' с частотой '{frequency}'.")
        await state.clear()
    else:  # Неожиданный тип
        with next(get_session()) as db_session:
            log_user_action(db_session, telegram_id, "subscribe_error_type", log_details)
        await callback_query.message.edit_text("Произошла ошибка выбора типа. Пожалуйста, попробуйте снова.")
        await state.clear()
    # Логируем сам факт выбора типа, если не залогировали внутри блока if/else
    # Здесь не нужно, т.к. логируем в каждом блоке или перед ним


@dp.callback_query(StateFilter(SubscriptionStates.choosing_info_type), F.data == "subscribe_fsm_cancel")
async def callback_fsm_cancel_process(callback_query: types.CallbackQuery, state: FSMContext):
    telegram_id = callback_query.from_user.id
    with next(get_session()) as db_session:
        log_user_action(db_session, telegram_id, "subscribe_fsm_cancel", "Cancelled type choice by button")
    logger.info(f"Пользователь {telegram_id} отменил процесс подписки кнопкой 'Отмена'.")
    await callback_query.answer()
    await callback_query.message.edit_text("Процесс подписки отменен.")
    await state.clear()


@dp.message(StateFilter(SubscriptionStates.entering_city_weather), F.text)
async def process_city_for_weather_subscription(message: types.Message, state: FSMContext):
    city_name = message.text.strip();
    telegram_id = message.from_user.id
    user_data = await state.get_data();
    info_type = user_data.get("info_type", "unknown")
    log_details = f"Input for {info_type}: {city_name}"

    with next(get_session()) as db_session:
        if not city_name:
            await message.reply("Название города не может быть пустым...")
            log_user_action(db_session, telegram_id, "subscribe_city_empty", log_details)
            return  # Остаемся в состоянии

        logger.info(f"Пользователь {telegram_id} ввел город '{city_name}' для подписки на '{info_type}'.")
        frequency = "daily"
        db_user = create_user_if_not_exists(db_session, telegram_id)
        existing_subscription = get_subscription_by_user_and_type(db_session, db_user.id, info_type, city_name)
        if existing_subscription:
            await message.answer(f"Вы уже подписаны на '{info_type}' для города '{html.escape(city_name)}'.")
            log_user_action(db_session, telegram_id, "subscribe_attempt_duplicate", log_details)
        else:
            create_subscription(db_session, db_user.id, info_type, frequency, city_name)
            log_user_action(db_session, telegram_id, "subscribe_confirm",
                            f"Type: {info_type}, City: {city_name}, Freq: {frequency}")
            await message.answer(
                f"Вы успешно подписались на '{info_type}' для города '{html.escape(city_name)}' с частотой '{frequency}'.")
        await state.clear()


@dp.message(StateFilter(SubscriptionStates.entering_city_events), F.text)
async def process_city_for_events_subscription(message: types.Message, state: FSMContext):
    city_arg = message.text.strip();
    telegram_id = message.from_user.id
    user_data = await state.get_data();
    info_type = user_data.get("info_type", "unknown")
    log_details = f"Input for {info_type}: {city_arg}"

    with next(get_session()) as db_session:
        if not city_arg:
            await message.reply("Название города не может быть пустым...")
            log_user_action(db_session, telegram_id, "subscribe_city_empty", log_details)
            return  # Остаемся в состоянии

        location_slug = KUDAGO_LOCATION_SLUGS.get(city_arg.lower())
        if not location_slug:
            await message.reply(
                f"К сожалению, не знаю событий для города '{html.escape(city_arg)}'...\nПопробуйте: Москва, Санкт-Петербург...")
            log_user_action(db_session, telegram_id, "subscribe_city_unsupported", log_details)
            return  # Остаемся в состоянии для повторного ввода

        log_details += f", slug: {location_slug}"
        logger.info(
            f"Пользователь {telegram_id} ввел город '{city_arg}' (slug: {location_slug}) для подписки на '{info_type}'.")
        frequency = "daily"
        db_user = create_user_if_not_exists(db_session, telegram_id)
        existing_subscription = get_subscription_by_user_and_type(db_session, db_user.id, info_type, location_slug)
        if existing_subscription:
            await message.answer(f"Вы уже подписаны на '{info_type}' для города '{html.escape(city_arg)}'.")
            log_user_action(db_session, telegram_id, "subscribe_attempt_duplicate", log_details)
        else:
            create_subscription(db_session, db_user.id, info_type, frequency, location_slug)
            log_user_action(db_session, telegram_id, "subscribe_confirm",
                            f"Type: {info_type}, City: {city_arg} (slug: {location_slug}), Freq: {frequency}")
            await message.answer(
                f"Вы успешно подписались на '{info_type}' для города '{html.escape(city_arg)}' с частотой '{frequency}'.")
        await state.clear()


@dp.message(Command('mysubscriptions'))
async def process_mysubscriptions_command(message: types.Message):
    telegram_id = message.from_user.id
    with next(get_session()) as db_session:
        log_user_action(db_session, telegram_id, "/mysubscriptions")
        db_user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if not db_user: await message.answer("Не удалось найти информацию о вас..."); return
        subscriptions = get_subscriptions_by_user_id(session=db_session, user_id=db_user.id)
        if not subscriptions: await message.answer("У вас пока нет активных подписок..."); return
        response_lines = ["<b>📋 Ваши активные подписки:</b>"]
        for i, sub in enumerate(subscriptions):
            sub_details_str = "";
            freq_str = html.escape(sub.frequency or 'ежедн.')
            if sub.info_type == INFO_TYPE_WEATHER:
                sub_details_str = f"Погода для города: <b>{html.escape(sub.details or 'Не указан')}</b>"
            elif sub.info_type == INFO_TYPE_NEWS:
                sub_details_str = "Новости (Россия)"
            elif sub.info_type == INFO_TYPE_EVENTS:
                city_display_name = sub.details
                for name, slug_val in KUDAGO_LOCATION_SLUGS.items():
                    if slug_val == sub.details: city_display_name = name.capitalize(); break
                sub_details_str = f"События в городе: <b>{html.escape(city_display_name)}</b>"
            else:
                sub_details_str = f"Тип: {html.escape(sub.info_type)}"
            response_lines.append(f"{i + 1}. {sub_details_str} ({freq_str})")
        await message.answer("\n".join(response_lines))


@dp.message(Command('unsubscribe'))
async def process_unsubscribe_command_start(message: types.Message,
                                            state: FSMContext):  # state нужен для единообразия, хотя здесь не используется
    telegram_id = message.from_user.id
    with next(get_session()) as db_session:
        log_user_action(db_session, telegram_id, "/unsubscribe", "Start unsubscribe process")
        db_user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if not db_user: await message.answer("Не удалось найти информацию о вас..."); return
        subscriptions = get_subscriptions_by_user_id(session=db_session, user_id=db_user.id)
        if not subscriptions: await message.answer("У вас нет активных подписок для отмены."); return
        keyboard_buttons = []
        for sub in subscriptions:
            sub_details_str = "";
            freq_str = html.escape(sub.frequency or 'ежедн.')
            if sub.info_type == INFO_TYPE_WEATHER:
                sub_details_str = f"Погода: {html.escape(sub.details or 'Город?')}"
            elif sub.info_type == INFO_TYPE_NEWS:
                sub_details_str = "Новости (Россия)"
            elif sub.info_type == INFO_TYPE_EVENTS:
                city_display_name = sub.details
                for name, slug_val in KUDAGO_LOCATION_SLUGS.items():
                    if slug_val == sub.details: city_display_name = name.capitalize(); break
                sub_details_str = f"События: {html.escape(city_display_name)}"
            else:
                sub_details_str = f"{html.escape(sub.info_type)}"
            keyboard_buttons.append([InlineKeyboardButton(text=f"❌ {sub_details_str} ({freq_str})",
                                                          callback_data=f"unsubscribe_confirm:{sub.id}")])
        keyboard_buttons.append(
            [InlineKeyboardButton(text="Отменить операцию", callback_data="unsubscribe_action_cancel")])
        await message.answer("Выберите подписку, от которой хотите отписаться:",
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))


@dp.callback_query(F.data.startswith("unsubscribe_confirm:"))
async def process_unsubscribe_confirm(callback_query: types.CallbackQuery, state: FSMContext):  # state для единообразия
    await callback_query.answer()
    subscription_id = int(callback_query.data.split(":")[1]);
    telegram_id = callback_query.from_user.id
    log_details = f"Subscription ID to delete: {subscription_id}"
    with next(get_session()) as db_session:
        db_user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if not db_user: await callback_query.message.edit_text("Ошибка: пользователь не найден."); log_user_action(
            db_session, telegram_id, "unsubscribe_error", f"{log_details}, user_not_found"); return

        subscription_to_check = db_session.get(Subscription, subscription_id)
        if not subscription_to_check or subscription_to_check.user_id != db_user.id:
            await callback_query.message.edit_text("Ошибка: это не ваша подписка или она не найдена.");
            log_user_action(db_session, telegram_id, "unsubscribe_error", f"{log_details}, sub_not_found_or_not_owner")
            return

        success = delete_subscription(session=db_session, subscription_id=subscription_id)
        if success:
            await callback_query.message.edit_text("Вы успешно отписались.")
            log_user_action(db_session, telegram_id, "unsubscribe_confirm_success", log_details)
        else:
            await callback_query.message.edit_text("Не удалось отписаться...")
            log_user_action(db_session, telegram_id, "unsubscribe_confirm_fail", log_details)


@dp.callback_query(F.data == "unsubscribe_action_cancel")
async def process_unsubscribe_action_cancel(callback_query: types.CallbackQuery,
                                            state: FSMContext):  # state для единообразия
    with next(get_session()) as db_session:
        log_user_action(db_session, callback_query.from_user.id, "unsubscribe_action_cancel")
    await callback_query.answer();
    await callback_query.message.edit_text("Операция отписки отменена.")


async def on_startup():
    logger.info("Бот запускается...")
    create_db_and_tables()

    # 1. Устанавливаем экземпляр бота для планировщика
    set_bot_instance(bot)

    # 2. Добавляем задачи в планировщик (но не запускаем его здесь)
    schedule_jobs()

    # 3. Запускаем планировщик, если он еще не запущен
    if not aps_scheduler.running:  # Используем импортированный объект aps_scheduler
        try:
            aps_scheduler.start()
            logger.info("Планировщик APScheduler успешно запущен из on_startup.")
        except Exception as e:
            logger.error(f"Ошибка при запуске планировщика из on_startup: {e}", exc_info=True)
    else:
        logger.info("Планировщик APScheduler уже был запущен.")

    commands_to_set = [
        types.BotCommand(command="start", description="🚀 Запуск и регистрация"),
        types.BotCommand(command="help", description="❓ Помощь по командам"),
        types.BotCommand(command="weather", description="☀️ Узнать погоду (город)"),
        types.BotCommand(command="news", description="📰 Последние новости (Россия)"),
        types.BotCommand(command="events", description="🎉 События (город)"),
        types.BotCommand(command="subscribe", description="🔔 Подписаться на рассылку"),
        types.BotCommand(command="mysubscriptions", description="📜 Мои подписки"),
        types.BotCommand(command="unsubscribe", description="🔕 Отписаться от рассылки"),
        types.BotCommand(command="cancel", description="❌ Отменить текущее действие"),
    ]
    try:
        await bot.set_my_commands(commands_to_set)
        logger.info("Команды бота успешно установлены в меню Telegram.")
    except Exception as e:
        logger.error(f"Ошибка при установке команд бота: {e}")
    logger.info("Бот успешно запущен!")

async def on_shutdown():
    logger.info("Бот останавливается...")
    # shutdown_scheduler() вызывается через dp.shutdown.register(shutdown_scheduler)
    logger.info("Бот остановлен.")


if __name__ == '__main__':
    # Импорты для планировщика здесь больше не нужны, т.к. set_bot_instance и schedule_jobs вызываются в on_startup
    # А сам scheduler импортирован на уровне модуля как aps_scheduler
    # from app.scheduler.main import schedule_jobs, shutdown_scheduler, set_bot_instance, scheduler as aps_scheduler

    dp.startup.register(on_startup)  # on_startup теперь отвечает за настройку и запуск планировщика
    dp.shutdown.register(shutdown_scheduler)  # Регистрируем shutdown_scheduler из модуля scheduler.main
    # dp.shutdown.register(on_shutdown) # Локальный on_shutdown для логов самого бота

    asyncio.run(dp.start_polling(bot, skip_updates=True))