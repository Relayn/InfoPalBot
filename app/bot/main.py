"""
Главный модуль Telegram-бота InfoPalBot.
Отвечает за инициализацию бота, диспетчера, обработку команд и сообщений от пользователей,
управление состояниями (FSM) для многошаговых операций (например, подписка),
а также запуск и остановку фоновых задач планировщика.

Основные компоненты:
1. Инициализация бота и диспетчера
2. Определение состояний FSM для многошаговых операций
3. Обработчики команд и сообщений
4. Функции для работы с базой данных
5. Функции для взаимодействия с внешними API
6. Функции для логирования действий пользователей

Пример использования:
    # Запуск бота
    asyncio.run(main())

    # Обработка команды /start
    @dp.message(Command("start"))
    async def process_start_command(message: types.Message):
        await message.answer("Привет!")
"""

import logging  # Для логирования событий и ошибок
import asyncio  # Для асинхронного программирования (используется aiogram и httpx)
import html  # Для экранирования HTML-сущностей в сообщениях
from typing import Optional, Dict, List, Union, Any  # Для аннотаций типов

# Компоненты Aiogram для создания бота и обработки событий
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import (
    DefaultBotProperties,
)  # Для настроек бота по умолчанию
from aiogram.enums import ParseMode  # Для указания режима разметки сообщений
from aiogram.filters import (
    Command,
    CommandObject,
    StateFilter,
)  # Фильтры для обработчиков
from aiogram.fsm.context import FSMContext  # Для управления состояниями диалога
from aiogram.fsm.state import State, StatesGroup  # Для определения групп состояний FSM
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)  # Для создания клавиатур

# Компоненты SQLModel для работы с БД
from sqlmodel import Session  # Для type hinting сессии БД

# Внутренние импорты проекта
from app.config import settings  # Настройки приложения (токены, URL БД и т.д.)
from app.database.session import (
    get_session,
    create_db_and_tables,
)  # Управление сессиями и создание таблиц
from app.database.crud import (  # Функции для работы с базой данных (CRUD)
    create_user_if_not_exists,
    get_user_by_telegram_id,
    create_subscription,
    get_subscriptions_by_user_id,
    get_subscription_by_user_and_type,
    delete_subscription,
    create_log_entry,
)
from app.database.models import User, Subscription  # Модели таблиц БД
from app.api_clients.weather import get_weather_data  # Клиент для API погоды
from app.api_clients.news import get_top_headlines  # Клиент для API новостей
from app.api_clients.events import get_kudago_events  # Клиент для API событий
from .constants import (
    INFO_TYPE_WEATHER,
    INFO_TYPE_NEWS,
    INFO_TYPE_EVENTS,
    KUDAGO_LOCATION_SLUGS,
)  # Общие константы

# Настройка стандартного логирования Python
# Уровень логирования (INFO, DEBUG и т.д.) берется из настроек приложения.
# Формат лога включает время, имя логгера, уровень и сообщение.
logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),  # Убедимся, что уровень в верхнем регистре
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
# Получаем экземпляр логгера для текущего модуля
logger = logging.getLogger(__name__)

# Настройки по умолчанию для отправки сообщений ботом (например, всегда использовать HTML разметку)
default_bot_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)
# Инициализация объекта бота с токеном из настроек и свойствами по умолчанию
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=default_bot_properties)
# Инициализация диспетчера для обработки входящих обновлений
dp = Dispatcher()


# KUDAGO_LOCATION_SLUGS импортируется из .constants, здесь определение не нужно.
# Если бы он не был в constants, то здесь:
# KUDAGO_LOCATION_SLUGS: Dict[str, str] = { ... }


# Определяем состояния (FSM) для процесса подписки
class SubscriptionStates(StatesGroup):
    """
    Состояния для конечного автомата (FSM) управления процессом подписки пользователя.

    Состояния используются для управления многошаговым процессом подписки:
    1. choosing_info_type: Пользователь выбирает тип информации (погода, новости, события)
    2. entering_city_weather: Пользователь вводит город для подписки на погоду
    3. entering_city_events: Пользователь вводит город для подписки на события
    4. choosing_frequency: Пользователь выбирает частоту рассылки

    Note:
        - Состояния используются в обработчиках команд и сообщений
        - Переход между состояниями происходит через FSMContext
        - Состояния очищаются после завершения процесса или отмены
    """

    choosing_info_type = (
        State()
    )  # Пользователь выбирает тип информации (погода, новости, события)
    entering_city_weather = State()  # Пользователь вводит город для подписки на погоду
    entering_city_events = State()  # Пользователь вводит город для подписки на события
    choosing_frequency = State()  # Пользователь выбирает частоту рассылки


def get_frequency_keyboard() -> InlineKeyboardMarkup:
    """
    Создает и возвращает inline-клавиатуру для выбора частоты уведомлений.
    """
    buttons = [
        [
            InlineKeyboardButton(text="Раз в 3 часа", callback_data="frequency:3"),
            InlineKeyboardButton(text="Раз в 6 часов", callback_data="frequency:6"),
        ],
        [
            InlineKeyboardButton(text="Раз в 12 часов", callback_data="frequency:12"),
            InlineKeyboardButton(text="Раз в 24 часа", callback_data="frequency:24"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="subscribe_fsm_cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def log_user_action(
    db_session: Session, telegram_id: int, command: str, details: Optional[str] = None
):
    """
    Вспомогательная функция для создания записи в логе базы данных о действии пользователя.

    Функция:
    1. Находит пользователя в БД по его Telegram ID
    2. Создает запись в логе с информацией о действии
    3. Обрабатывает возможные ошибки без прерывания основного потока

    Args:
        db_session (Session): Активная сессия базы данных SQLModel.
        telegram_id (int): Telegram ID пользователя, совершившего действие.
        command (str): Строковое представление команды или типа действия
                      (например, "/start", "subscribe_weather").
        details (Optional[str]): Дополнительные детали действия
                                (например, аргументы команды, результат).
                                По умолчанию None.

    Note:
        - Если пользователь не найден в БД, запись в лог все равно создается
        - Ошибки при записи в лог логируются, но не прерывают основное действие
        - Функция используется во всех обработчиках команд для аудита действий
    """
    # Пытаемся найти пользователя в БД по его Telegram ID, чтобы связать лог с внутренним user_id
    user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
    user_db_id: Optional[int] = (
        user.id if user else None
    )  # Если пользователь найден, используем его ID, иначе None

    try:
        # Создаем запись в логе
        create_log_entry(
            session=db_session, user_id=user_db_id, command=command, details=details
        )
    except Exception as e:
        # Если произошла ошибка при записи в лог, логируем ее в консоль/файл, но не прерываем основное действие
        logger.error(
            f"Не удалось создать запись в логе для пользователя {telegram_id}, команда {command}: {e}",
            exc_info=True,
        )


# Этот код является продолжением Части 1 файла app/bot/main.py

# ... (код до log_user_action включительно, как в Части 1) ...

# --- ОБРАБОТЧИКИ ОСНОВНЫХ КОМАНД ---


@dp.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel_any_state(message: types.Message, state: FSMContext):
    """
    Обрабатывает команду /cancel в любом состоянии FSM (или без состояния).

    Функция:
    1. Отменяет текущее многошаговое действие пользователя
    2. Очищает состояние FSM
    3. Удаляет клавиатуру
    4. Логирует действие в БД

    Args:
        message (types.Message): Объект сообщения от пользователя.
        state (FSMContext): Контекст конечного автомата для управления состояниями.

    Note:
        - Команда работает в любом состоянии FSM
        - Если состояние отсутствует, пользователь получает соответствующее сообщение
        - После отмены все состояния очищаются
    """
    telegram_id: int = message.from_user.id
    current_state_str: Optional[str] = await state.get_state()
    log_details: str = f"State before cancel: {current_state_str}"

    # Логируем попытку отмены
    with get_session() as db_session:
        log_user_action(db_session, telegram_id, "/cancel", log_details)

    if current_state_str is None:
        # Если пользователь не находится ни в каком состоянии, сообщаем, что отменять нечего
        await message.answer(
            "Нет активного действия для отмены.", reply_markup=ReplyKeyboardRemove()
        )
        return

    logger.info(
        f"Пользователь {telegram_id} отменил действие командой /cancel из состояния {current_state_str}."
    )
    await state.clear()  # Очищаем состояние FSM
    await message.answer("Действие отменено.", reply_markup=ReplyKeyboardRemove())


@dp.message(Command("start"), StateFilter("*"))
async def process_start_command(message: types.Message, state: FSMContext):
    """
    Обрабатывает команду /start.

    Функция:
    1. Приветствует пользователя
    2. Регистрирует его в системе (если новый)
    3. Сбрасывает любое активное состояние FSM
    4. Логирует действие в БД

    Args:
        message (types.Message): Объект сообщения от пользователя.
        state (FSMContext): Контекст конечного автомата для управления состояниями.

    Note:
        - Команда работает в любом состоянии FSM
        - Приветственное сообщение включает имя пользователя
        - Новые пользователи автоматически регистрируются в БД
        - Все активные состояния очищаются при старте
    """
    telegram_id: int = message.from_user.id
    logger.info(
        f"Команда /start вызвана пользователем {telegram_id}. Текущее состояние: {await state.get_state()}"
    )
    await state.clear()  # Важно сбрасывать состояние при /start

    db_user_internal_id: Optional[int] = (
        None  # Для логирования ошибки, если пользователь еще не создан
    )
    log_command: str = "/start"
    log_details: Optional[str] = "User started/restarted the bot"

    try:
        with get_session() as db_session:
            # Получаем или создаем пользователя в БД
            db_user = create_user_if_not_exists(
                session=db_session, telegram_id=telegram_id
            )
            db_user_internal_id = db_user.id
            logger.info(
                f"Обработана команда /start от пользователя {telegram_id}. Пользователь в БД: {db_user_internal_id}"
            )
            # Логируем успешное выполнение команды
            log_user_action(db_session, telegram_id, log_command, log_details)

        await message.answer(
            f"Привет, {message.from_user.full_name}! Я InfoPalBot. Я могу предоставить тебе актуальную информацию.\n"
            f"Используй /help, чтобы увидеть список доступных команд."
        )
    except Exception as e:
        logger.error(
            f"Ошибка при обработке команды /start для пользователя {telegram_id}: {e}",
            exc_info=True,
        )
        # Формируем детали для лога ошибки
        error_log_details = f"User ID {db_user_internal_id if db_user_internal_id else 'unknown'}, error: {str(e)[:150]}"
        try:  # Отдельная попытка залогировать критическую ошибку
            with get_session() as db_session_err:
                log_user_action(
                    db_session_err,
                    telegram_id,
                    f"{log_command}_error",
                    error_log_details,
                )
        except Exception as log_e:
            logger.error(f"Не удалось залогировать ошибку {log_command}: {log_e}")
        await message.answer(
            "Произошла ошибка при обработке вашего запроса. Попробуйте позже."
        )


@dp.message(Command("help"))
async def process_help_command(message: types.Message):
    """
    Обрабатывает команду /help.
    Отправляет пользователю справочное сообщение со списком доступных команд.
    """
    telegram_id: int = message.from_user.id
    help_text: str = (
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
    # Логируем действие
    with get_session() as db_session:
        log_user_action(db_session, telegram_id, "/help")


@dp.message(Command("weather"))
async def process_weather_command(message: types.Message, command: CommandObject):
    """
    Обрабатывает команду /weather [город].
    Запрашивает и отображает погоду для указанного города, логирует запрос и результат.
    """
    city_name_arg: Optional[str] = (
        command.args
    )  # Аргументы команды (все, что после /weather)
    telegram_id: int = message.from_user.id
    log_command: str = "/weather"
    log_details: str = "N/A"  # Будет перезаписано

    try:
        with get_session() as db_session:
            if not city_name_arg:
                # Если город не указан, отправляем инструкцию
                await message.reply("Пожалуйста, укажите название города...")
                logger.info(
                    f"Команда /weather вызвана без указания города пользователем {telegram_id}."
                )
                log_details = "Город не указан"
                log_user_action(db_session, telegram_id, log_command, log_details)
                return

            city_name_clean: str = city_name_arg.strip()
            log_details = f"город: {city_name_clean}"  # Основная деталь для лога
            logger.info(
                f"Пользователь {telegram_id} запросил погоду для города: {city_name_clean}"
            )
            await message.reply(
                f"Запрашиваю погоду для города <b>{html.escape(city_name_clean)}</b>..."
            )

            # Получаем данные о погоде
            weather_data: Optional[Dict[str, Any]] = await get_weather_data(
                city_name_clean
            )
            log_status_suffix: str = (
                ""  # Добавка к деталям лога в зависимости от результата
            )

            if weather_data and not weather_data.get("error"):
                try:
                    # Извлекаем и форматируем данные для ответа
                    description: str = weather_data["weather"][0][
                        "description"
                    ].capitalize()
                    temp: float = weather_data["main"]["temp"]
                    feels_like: float = weather_data["main"]["feels_like"]
                    humidity: int = weather_data["main"]["humidity"]
                    wind_speed: float = weather_data["wind"]["speed"]
                    wind_deg: Optional[int] = weather_data["wind"].get("deg")
                    wind_direction_str: str = ""
                    if wind_deg is not None:
                        directions = [
                            "Северный",
                            "С-В",
                            "Восточный",
                            "Ю-В",
                            "Южный",
                            "Ю-З",
                            "Западный",
                            "С-З",
                        ]
                        wind_direction_str = (
                            f", {directions[int((wind_deg % 360) / 45)]}"
                        )

                    response_text: str = (
                        f"<b>Погода в городе {html.escape(weather_data.get('name', city_name_clean))}:</b>\n"
                        f"🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n"
                        f"💧 Влажность: {humidity}%\n"
                        f"💨 Ветер: {wind_speed} м/с{wind_direction_str}\n"
                        f"☀️ Описание: {description}"
                    )
                    await message.answer(response_text)
                    log_status_suffix = ", успех"
                except KeyError as e:
                    logger.error(
                        f"Ошибка парсинга данных о погоде для {city_name_clean}: ключ {e}. Данные: {weather_data}",
                        exc_info=True,
                    )
                    await message.answer("Не удалось обработать данные о погоде...")
                    log_status_suffix = f", ошибка парсинга: {str(e)[:50]}"
                except Exception as e:  # Любая другая ошибка при формировании ответа
                    logger.error(
                        f"Непредвиденная ошибка при формировании ответа о погоде для {city_name_clean}: {e}",
                        exc_info=True,
                    )
                    await message.answer("Произошла ошибка при отображении погоды.")
                    log_status_suffix = f", ошибка отображения: {str(e)[:50]}"

            elif weather_data and weather_data.get("error"):  # Ошибка от API клиента
                error_message_text: str = weather_data.get(
                    "message", "Неизвестная ошибка API."
                )
                status_code: Optional[int] = weather_data.get("status_code")
                if status_code == 404:
                    await message.reply(
                        f"Город <b>{html.escape(city_name_clean)}</b> не найден..."
                    )
                elif status_code == 401:  # Ошибка авторизации (API ключ)
                    await message.reply("Проблема с доступом к сервису погоды...")
                    logger.critical(
                        "API ключ OpenWeatherMap недействителен или неверно настроен!"
                    )
                else:
                    await message.reply(
                        f"Не удалось получить погоду: {html.escape(error_message_text)}"
                    )
                logger.warning(
                    f"Ошибка API погоды для {city_name_clean} (user {telegram_id}): {error_message_text}"
                )
                log_status_suffix = f", ошибка API: {error_message_text[:50]}"
            else:  # get_weather_data вернул None или пустой словарь без "error"
                await message.reply("Не удалось получить данные о погоде...")
                logger.error(
                    f"get_weather_data вернул None или неожиданный ответ для {city_name_clean} (user {telegram_id})."
                )
                log_status_suffix = ", нет данных от API"

            # Финальное логирование действия
            log_user_action(
                db_session, telegram_id, log_command, log_details + log_status_suffix
            )

    except Exception as e:  # Глобальный обработчик ошибок для всей команды
        logger.error(
            f"Критическая ошибка в process_weather_command для {telegram_id}, город '{city_name_arg}': {e}",
            exc_info=True,
        )
        await message.answer(
            "Произошла внутренняя ошибка сервера. Пожалуйста, попробуйте позже."
        )
        try:  # Попытка залогировать критическую ошибку
            with get_session() as db_session_err:
                log_user_action(
                    db_session_err,
                    telegram_id,
                    f"{log_command}_critical_error",
                    str(e)[:250],
                )
        except Exception as log_e:
            logger.error(
                f"Не удалось залогировать критическую ошибку {log_command}: {log_e}"
            )


@dp.message(Command("news"))
async def process_news_command(message: types.Message):
    """
    Обрабатывает команду /news. Запрашивает и отображает главные новости для России.
    Логирует запрос и результат.
    """
    telegram_id: int = message.from_user.id
    logger.info(f"Пользователь {telegram_id} запросил новости.")
    await message.reply("Запрашиваю последние главные новости для России...")

    log_command: str = "/news"
    log_status_details: str = "unknown_error"  # Статус выполнения для лога
    try:
        with get_session() as db_session:
            # Получаем новости через API клиент
            articles_or_error: Optional[List[Dict[str, Any]]] | Dict[str, Any] = (
                await get_top_headlines(country="ru", page_size=5)
            )

            if isinstance(articles_or_error, list) and articles_or_error:
                # Успешно получены статьи
                response_lines: List[str] = [
                    "<b>📰 Последние главные новости (Россия):</b>"
                ]
                for i, article in enumerate(articles_or_error):
                    title: str = html.escape(article.get("title", "Без заголовка"))
                    url: str = article.get("url", "#")
                    source: str = html.escape(
                        article.get("source", {}).get("name", "Неизвестный источник")
                    )
                    response_lines.append(
                        f"{i + 1}. <a href='{url}'>{title}</a> ({source})"
                    )
                await message.answer(
                    "\n".join(response_lines), disable_web_page_preview=True
                )
                logger.info(f"Успешно отправлены новости пользователю {telegram_id}.")
                log_status_details = "success"
            elif isinstance(articles_or_error, list) and not articles_or_error:
                # API вернул пустой список (нет новостей)
                await message.reply(
                    "На данный момент нет главных новостей для отображения."
                )
                logger.info(
                    f"Главных новостей для России не найдено (пользователь {telegram_id})."
                )
                log_status_details = "no_articles_found"
            elif isinstance(articles_or_error, dict) and articles_or_error.get("error"):
                # API клиент вернул словарь с ошибкой
                error_message_text: str = articles_or_error.get(
                    "message", "Неизвестная ошибка API."
                )
                await message.reply(
                    f"Не удалось получить новости: {html.escape(error_message_text)}"
                )
                logger.warning(
                    f"Ошибка API новостей (user {telegram_id}): {error_message_text}"
                )
                log_status_details = f"api_error: {error_message_text[:100]}"
            else:  # Неожиданный формат ответа от API клиента
                await message.reply("Не удалось получить данные о новостях...")
                logger.error(
                    f"get_top_headlines вернул неожиданный ответ для России (user {telegram_id}): {articles_or_error}"
                )
                log_status_details = "unexpected_api_response"

            # Логируем действие
            log_user_action(db_session, telegram_id, log_command, log_status_details)

    except Exception as e:  # Глобальный обработчик ошибок
        logger.error(
            f"Критическая ошибка в process_news_command для {telegram_id}: {e}",
            exc_info=True,
        )
        await message.answer("Произошла внутренняя ошибка сервера...")
        try:  # Попытка залогировать критическую ошибку
            with get_session() as db_session_err:
                log_user_action(
                    db_session_err,
                    telegram_id,
                    f"{log_command}_critical_error",
                    str(e)[:250],
                )
        except Exception as log_e:
            logger.error(
                f"Не удалось залогировать критическую ошибку {log_command}: {log_e}"
            )


# ... (продолжение в Части 3) ...
# Этот код является продолжением Части 2 файла app/bot/main.py

# ... (код до process_news_command включительно, как в Части 2) ...


@dp.message(Command("events"))
async def process_events_command(message: types.Message, command: CommandObject):
    """
    Обрабатывает команду /events [город].
    Запрашивает и отображает актуальные события KudaGo для указанного города.
    Логирует запрос и результат.
    """
    city_arg: Optional[str] = command.args
    telegram_id: int = message.from_user.id
    log_command: str = "/events"
    log_details: str = "N/A"  # Значение по умолчанию

    try:
        with get_session() as db_session:
            if not city_arg:
                await message.reply(
                    "Пожалуйста, укажите город...\nДоступные города: Москва, Санкт-Петербург..."
                )
                logger.info(
                    f"Команда /events вызвана без указания города пользователем {telegram_id}."
                )
                log_details = "Город не указан"
                log_user_action(db_session, telegram_id, log_command, log_details)
                return

            city_arg_clean: str = city_arg.strip()
            city_name_lower: str = city_arg_clean.lower()
            location_slug: Optional[str] = KUDAGO_LOCATION_SLUGS.get(city_name_lower)
            log_details = f"город: {city_arg_clean}"

            if not location_slug:
                await message.reply(
                    f"К сожалению, не знаю событий для города '{html.escape(city_arg_clean)}'...\nПопробуйте: Москва, Санкт-Петербург..."
                )
                logger.info(
                    f"Пользователь {telegram_id} запросил события для неподдерживаемого города: {city_arg_clean}"
                )
                log_details += ", город не поддерживается"
                log_user_action(db_session, telegram_id, log_command, log_details)
                return

            logger.info(
                f"Пользователь {telegram_id} запросил события KudaGo для города: {city_arg_clean} (slug: {location_slug})"
            )
            await message.reply(
                f"Запрашиваю актуальные события для города <b>{html.escape(city_arg_clean)}</b>..."
            )

            events_result: Optional[List[Dict[str, Any]]] | Dict[str, Any] = (
                await get_kudago_events(location=location_slug, page_size=5)
            )
            log_status_suffix: str = ""

            if isinstance(events_result, list) and events_result:
                response_lines: List[str] = [
                    f"<b>🎉 Актуальные события в городе {html.escape(city_arg_clean.capitalize())}:</b>"
                ]
                for i, event_data in enumerate(events_result):
                    title: str = html.escape(event_data.get("title", "Без заголовка"))
                    site_url: str = event_data.get("site_url", "#")
                    description_raw: str = event_data.get("description", "")
                    description: str = html.unescape(
                        description_raw.replace("<p>", "")
                        .replace("</p>", "")
                        .replace("<br>", "\n")
                    ).strip()

                    event_str: str = f"{i + 1}. <a href='{site_url}'>{title}</a>"
                    if description:
                        max_desc_len = 100
                        if len(description) > max_desc_len:
                            description = description[:max_desc_len] + "..."
                        event_str += f"\n   <i>{html.escape(description)}</i>"
                    response_lines.append(event_str)
                await message.answer(
                    "\n\n".join(response_lines), disable_web_page_preview=True
                )
                logger.info(
                    f"Успешно отправлены события KudaGo для {location_slug} пользователю {telegram_id}."
                )
                log_status_suffix = ", успех"
            elif isinstance(events_result, list) and not events_result:
                await message.reply(
                    f"Не найдено актуальных событий для города <b>{html.escape(city_arg_clean)}</b>."
                )
                logger.info(
                    f"Актуальных событий KudaGo для {location_slug} не найдено (пользователь {telegram_id})."
                )
                log_status_suffix = ", не найдено"
            elif isinstance(events_result, dict) and events_result.get("error"):
                error_message_text: str = events_result.get(
                    "message", "Неизвестная ошибка API."
                )
                await message.reply(
                    f"Не удалось получить события: {html.escape(error_message_text)}"
                )
                logger.warning(
                    f"Ошибка API событий KudaGo для {location_slug} (user {telegram_id}): {error_message_text}"
                )
                log_status_suffix = f", ошибка API: {error_message_text[:70]}"
            else:
                await message.reply("Не удалось получить данные о событиях...")
                logger.error(
                    f"get_kudago_events вернул неожиданный ответ для {location_slug} (user {telegram_id}): {events_result}"
                )
                log_status_suffix = ", unexpected_api_response"

            log_user_action(
                db_session, telegram_id, log_command, log_details + log_status_suffix
            )

    except Exception as e:  # Глобальный обработчик ошибок
        logger.error(
            f"Критическая ошибка в process_events_command для {telegram_id}, город '{city_arg}': {e}",
            exc_info=True,
        )
        await message.answer("Произошла внутренняя ошибка сервера...")
        try:  # Попытка залогировать критическую ошибку
            with get_session() as db_session_err:
                log_user_action(
                    db_session_err,
                    telegram_id,
                    f"{log_command}_critical_error",
                    str(e)[:250],
                )
        except Exception as log_e:
            logger.error(
                f"Не удалось залогировать критическую ошибку {log_command}: {log_e}"
            )


# --- ОБРАБОТЧИКИ ДЛЯ ПОДПИСОК (FSM) ---


@dp.message(
    Command("subscribe"), StateFilter(None)
)  # Срабатывает только если нет активного состояния
async def process_subscribe_command_start(message: types.Message, state: FSMContext):
    """
    Начинает процесс подписки пользователя. Предлагает выбрать тип информации.
    Устанавливает начальное состояние FSM.
    """
    telegram_id: int = message.from_user.id
    with get_session() as db_session:
        # Проверяем, не достиг ли пользователь лимита подписок
        user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if user and len(user.subscriptions) >= 3:
            await message.answer(
                "У вас уже 3 активных подписки. Это максимальное количество.\n"
                "Вы можете удалить одну из существующих подписок с помощью /unsubscribe."
            )
            log_user_action(
                db_session,
                telegram_id,
                "/subscribe",
                "Subscription limit reached",
            )
            return

        log_user_action(
            db_session, telegram_id, "/subscribe", "Start subscription process"
        )
    logger.info(
        f"Пользователь {telegram_id} начал процесс подписки командой /subscribe."
    )

    keyboard_buttons = [
        [
            InlineKeyboardButton(
                text="🌦️ Погода", callback_data=f"subscribe_type:{INFO_TYPE_WEATHER}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📰 Новости (Россия)",
                callback_data=f"subscribe_type:{INFO_TYPE_NEWS}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🎉 События", callback_data=f"subscribe_type:{INFO_TYPE_EVENTS}"
            )
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="subscribe_fsm_cancel")
        ],  # Кнопка отмены FSM
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(
        "На какой тип информации вы хотите подписаться?", reply_markup=keyboard
    )
    await state.set_state(
        SubscriptionStates.choosing_info_type
    )  # Переход в состояние выбора типа


@dp.callback_query(
    StateFilter(SubscriptionStates.choosing_info_type),
    F.data.startswith("subscribe_type:"),
)
async def process_info_type_choice(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """
    Обрабатывает выбор типа информации (погода, новости, события) на первом шаге подписки.

    Функция:
    1. Получает выбранный тип информации из callback_data.
    2. Сохраняет тип в FSM.
    3. В зависимости от типа:
        - Для новостей: переходит к выбору частоты.
        - Для погоды/событий: запрашивает город у пользователя.
    4. Логирует действие пользователя.

    Args:
        callback_query (types.CallbackQuery): Объект callback-запроса от кнопки.
        state (FSMContext): Контекст конечного автомата.
    """
    telegram_id = callback_query.from_user.id
    # Извлекаем тип информации из callback_data (например, "subscribe_type:weather" -> "weather")
    info_type = callback_query.data.split(":")[1]
    logger.info(f"Пользователь {telegram_id} выбрал тип подписки: {info_type}")

    await state.update_data(info_type=info_type)

    with get_session() as db_session:
        log_user_action(
            db_session,
            telegram_id,
            "subscribe_type_selected",
            f"Type chosen: {info_type}",
        )

        # Проверяем, есть ли уже активная подписка такого типа (без города)
        # Это актуально для новостей, где подписка не зависит от города.
        if info_type == INFO_TYPE_NEWS:
            existing_sub = get_subscription_by_user_and_type(
                session=db_session,
                user_id=get_user_by_telegram_id(
                    session=db_session, telegram_id=telegram_id
                ).id,
                info_type=info_type,
            )
            if existing_sub and existing_sub.status == "active":
                await callback_query.message.edit_text(
                    "Вы уже подписаны на 'Новости'.\n"
                    "Для управления подписками используйте /mysubscriptions."
                )
                await state.clear()
                return

    # В зависимости от типа информации, переходим к следующему шагу
    if info_type == INFO_TYPE_WEATHER:
        await callback_query.message.edit_text(
            "Вы выбрали 'Погода'.\nПожалуйста, введите название города..."
        )
        await state.set_state(SubscriptionStates.entering_city_weather)
    elif info_type == INFO_TYPE_EVENTS:
        await callback_query.message.edit_text(
            "Вы выбрали 'События'.\nПожалуйста, введите название города (например, Москва, спб)."
        )
        await state.set_state(SubscriptionStates.entering_city_events)
    elif info_type == INFO_TYPE_NEWS:
        # Для новостей город не нужен, сразу переходим к выбору частоты
        await callback_query.message.edit_text(
            "Вы выбрали 'Новости'.\nТеперь выберите частоту уведомлений:",
            reply_markup=get_frequency_keyboard(),
        )
        await state.set_state(SubscriptionStates.choosing_frequency)

    await callback_query.answer()


@dp.callback_query(
    StateFilter(SubscriptionStates.choosing_info_type), F.data == "subscribe_fsm_cancel"
)
async def callback_fsm_cancel_process(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """
    Обрабатывает нажатие кнопки "Отмена" в диалоге выбора типа подписки.
    """
    telegram_id: int = callback_query.from_user.id
    with get_session() as db_session:
        log_user_action(
            db_session,
            telegram_id,
            "subscribe_fsm_cancel",
            "Cancelled type choice by button",
        )
    logger.info(
        f"Пользователь {telegram_id} отменил процесс подписки кнопкой 'Отмена'."
    )
    await callback_query.answer()
    await callback_query.message.edit_text("Процесс подписки отменен.")
    await state.clear()


@dp.message(StateFilter(SubscriptionStates.entering_city_weather), F.text)
async def process_city_for_weather_subscription(
    message: types.Message, state: FSMContext
):
    """
    Обрабатывает ввод города для подписки на погоду.

    Функция:
    1. Проверяет, что введен непустой город.
    2. Проверяет, нет ли у пользователя уже активной подписки на этот город.
    3. Если всё хорошо, сохраняет город в FSM и переходит к выбору частоты.
    4. Если город невалиден или подписка уже есть, информирует пользователя.

    Args:
        message (types.Message): Объект сообщения от пользователя.
        state (FSMContext): Контекст конечного автомата.
    """
    telegram_id = message.from_user.id
    city_name = message.text.strip()

    if not city_name:
        await message.reply("Название города не может быть пустым...")
        # Состояние не меняем, даем пользователю попробовать снова
        return

    # Проверяем, есть ли уже подписка на погоду для этого города
    with get_session() as db_session:
        user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if user:
            existing_sub = get_subscription_by_user_and_type(
                session=db_session,
                user_id=user.id,
                info_type=INFO_TYPE_WEATHER,
                details=city_name,
            )
            if existing_sub and existing_sub.status == "active":
                await message.answer(
                    f"Вы уже подписаны на '{INFO_TYPE_WEATHER}' для города '{html.escape(city_name)}'."
                )
                log_user_action(
                    db_session,
                    telegram_id,
                    "subscribe_attempt_duplicate",
                    f"Type: {INFO_TYPE_WEATHER}, City input: {city_name}",
                )
                await state.clear()
                return

    # Если всё в порядке, сохраняем город и переходим к выбору частоты
    await state.update_data(details=city_name)
    await message.answer(
        f"Город '{html.escape(city_name)}' принят.\nТеперь выберите частоту уведомлений:",
        reply_markup=get_frequency_keyboard(),
    )
    await state.set_state(SubscriptionStates.choosing_frequency)


@dp.message(StateFilter(SubscriptionStates.entering_city_events), F.text)
async def process_city_for_events_subscription(
    message: types.Message, state: FSMContext
):
    """
    Обрабатывает ввод города для подписки на события.

    Функция:
    1. Проверяет, поддерживается ли введенный город (есть ли он в KUDAGO_LOCATION_SLUGS).
    2. Проверяет, нет ли у пользователя уже активной подписки на этот город (по slug).
    3. Если всё хорошо, сохраняет город и его slug в FSM, переходит к выбору частоты.
    4. Если город невалиден или подписка уже есть, информирует пользователя.

    Args:
        message (types.Message): Объект сообщения от пользователя.
        state (FSMContext): Контекст конечного автомата.
    """
    telegram_id = message.from_user.id
    city_name = message.text.strip()
    location_slug = KUDAGO_LOCATION_SLUGS.get(city_name.lower())

    if not location_slug:
        supported_cities = ", ".join(
            [city.capitalize() for city in KUDAGO_LOCATION_SLUGS.keys()]
        )
        await message.reply(
            f"К сожалению, не знаю событий для города '{html.escape(city_name)}'...\n"
            f"Попробуйте: {supported_cities}..."
        )
        with get_session() as db_session:
            log_user_action(
                db_session,
                telegram_id,
                "subscribe_city_unsupported",
                f"Type: {INFO_TYPE_EVENTS}, City input: {city_name}",
            )
        # Состояние не меняем, даем пользователю попробовать снова
        return

    # Проверяем, есть ли уже подписка на события для этого города (slug)
    with get_session() as db_session:
        user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if user:
            existing_sub = get_subscription_by_user_and_type(
                session=db_session,
                user_id=user.id,
                info_type=INFO_TYPE_EVENTS,
                details=location_slug,
            )
            if existing_sub and existing_sub.status == "active":
                await message.answer(
                    f"Вы уже подписаны на '{INFO_TYPE_EVENTS}' для города '{html.escape(city_name)}'."
                )
                log_user_action(
                    db_session,
                    telegram_id,
                    "subscribe_attempt_duplicate",
                    f"Type: {INFO_TYPE_EVENTS}, City input: {city_name}, slug: {location_slug}",
                )
                await state.clear()
                return

    # Если всё в порядке, сохраняем город и slug, переходим к выбору частоты
    await state.update_data(details=location_slug)
    await message.answer(
        f"Город '{html.escape(city_name)}' принят.\nТеперь выберите частоту уведомлений:",
        reply_markup=get_frequency_keyboard(),
    )
    await state.set_state(SubscriptionStates.choosing_frequency)


@dp.callback_query(
    StateFilter(SubscriptionStates.choosing_frequency), F.data.startswith("frequency:")
)
async def process_frequency_choice(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """
    Обрабатывает выбор частоты уведомлений и завершает процесс подписки.
    """
    telegram_id = callback_query.from_user.id
    try:
        frequency_hours = int(callback_query.data.split(":")[1])
    except (ValueError, IndexError):
        logger.warning(
            f"Некорректный callback для частоты от {telegram_id}: {callback_query.data}"
        )
        await callback_query.answer("Произошла ошибка, попробуйте снова.")
        return

    user_data = await state.get_data()
    info_type = user_data.get("info_type")
    details = user_data.get("details")

    with get_session() as db_session:
        user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if not user:
            logger.error(f"Не удалось найти пользователя {telegram_id} в БД.")
            await callback_query.message.edit_text(
                "Произошла ошибка: пользователь не найден. Пожалуйста, попробуйте /start."
            )
            await state.clear()
            return

        try:
            create_subscription(
                session=db_session,
                user_id=user.id,
                info_type=info_type,
                frequency=frequency_hours,
                details=details,
            )
            log_user_action(
                db_session,
                telegram_id,
                "subscribe_finish",
                f"Type: {info_type}, Freq: {frequency_hours}h, Details: {details}",
            )
            logger.info(
                f"Пользователь {telegram_id} успешно подписался на {info_type} с частотой {frequency_hours}ч."
            )

            await callback_query.message.edit_text(
                f"Вы успешно подписались на '{info_type}' с частотой раз в {frequency_hours} часа(ов)!\n"
                "Используйте /mysubscriptions для просмотра ваших подписок."
            )

        except Exception as e:
            logger.error(
                f"Ошибка создания подписки для пользователя {telegram_id}: {e}",
                exc_info=True,
            )
            await callback_query.message.edit_text(
                "Произошла ошибка при создании подписки. Попробуйте позже."
            )

    await state.clear()
    await callback_query.answer()


@dp.message(Command("mysubscriptions"))
async def process_mysubscriptions_command(message: types.Message):
    """
    Обрабатывает команду /mysubscriptions.
    Отображает пользователю список его активных подписок.
    """
    telegram_id: int = message.from_user.id
    log_command: str = "/mysubscriptions"
    log_details: Optional[str] = (
        None  # По умолчанию нет деталей, если нет ошибок/особых случаев
    )

    with get_session() as db_session:
        db_user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if not db_user:
            await message.answer("Не удалось найти информацию о вас...")
            log_details = "User not found"
            log_user_action(db_session, telegram_id, log_command, log_details)
            return

        subscriptions: List[Subscription] = get_subscriptions_by_user_id(
            session=db_session, user_id=db_user.id
        )
        if not subscriptions:
            await message.answer("У вас пока нет активных подписок...")
            log_details = "No active subscriptions"
            log_user_action(db_session, telegram_id, log_command, log_details)
            return

        response_lines: List[str] = ["<b>📋 Ваши активные подписки:</b>"]
        for i, sub in enumerate(subscriptions):
            sub_details_str: str = ""
            freq_str: str = html.escape(str(sub.frequency) or "ежедн.")
            if sub.info_type == INFO_TYPE_WEATHER:
                sub_details_str = f"Погода для города: <b>{html.escape(sub.details or 'Не указан')}</b>"
            elif sub.info_type == INFO_TYPE_NEWS:
                sub_details_str = "Новости (Россия)"
            elif sub.info_type == INFO_TYPE_EVENTS:
                city_display_name: str = (
                    sub.details or "Не указан"
                )  # slug или "Не указан"
                for name, slug_val in KUDAGO_LOCATION_SLUGS.items():
                    if slug_val == sub.details:
                        city_display_name = name.capitalize()
                        break
                sub_details_str = (
                    f"События в городе: <b>{html.escape(city_display_name)}</b>"
                )
            else:  # Общий случай для неизвестных типов подписок
                sub_details_str = f"Тип: {html.escape(sub.info_type)}"
                if sub.details:
                    sub_details_str += f", Детали: {html.escape(sub.details)}"
            response_lines.append(f"{i + 1}. {sub_details_str} ({freq_str})")

        await message.answer("\n".join(response_lines))
        log_details = f"Displayed {len(subscriptions)} subscriptions"
        log_user_action(db_session, telegram_id, log_command, log_details)


@dp.message(Command("unsubscribe"))
async def process_unsubscribe_command_start(
    message: types.Message, state: FSMContext
):  # state для единообразия, здесь не используется
    """
    Начинает процесс отписки. Отображает активные подписки пользователя с кнопками для отмены.
    """
    telegram_id: int = message.from_user.id
    log_details: str = "Start unsubscribe process"

    with get_session() as db_session:
        log_user_action(db_session, telegram_id, "/unsubscribe", log_details)
        db_user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if not db_user:
            await message.answer("Не удалось найти информацию о вас...")
            # Дополнительное логирование не требуется, т.к. log_user_action уже записал /unsubscribe
            return

        subscriptions: List[Subscription] = get_subscriptions_by_user_id(
            session=db_session, user_id=db_user.id
        )
        if not subscriptions:
            await message.answer("У вас нет активных подписок для отмены.")
            log_user_action(
                db_session,
                telegram_id,
                "/unsubscribe",
                "No active subscriptions to display",
            )  # Уточняем лог
            return

        keyboard_buttons: List[List[InlineKeyboardButton]] = []
        for sub in subscriptions:
            sub_details_str: str = ""
            freq_str: str = html.escape(str(sub.frequency) or "ежедн.")
            if sub.info_type == INFO_TYPE_WEATHER:
                sub_details_str = f"Погода: {html.escape(sub.details or 'Город?')}"
            elif sub.info_type == INFO_TYPE_NEWS:
                sub_details_str = "Новости (Россия)"
            elif sub.info_type == INFO_TYPE_EVENTS:
                city_display_name = sub.details or "Не указан"
                for name, slug_val in KUDAGO_LOCATION_SLUGS.items():
                    if slug_val == sub.details:
                        city_display_name = name.capitalize()
                        break
                sub_details_str = f"События: {html.escape(city_display_name)}"
            else:
                sub_details_str = f"{html.escape(sub.info_type)}"
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"❌ {sub_details_str} ({freq_str})",
                        callback_data=f"unsubscribe_confirm:{sub.id}",
                    )
                ]
            )

        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text="Отменить операцию", callback_data="unsubscribe_action_cancel"
                )
            ]
        )
        await message.answer(
            "Выберите подписку, от которой хотите отписаться:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        )
        # Логируем, что пользователю показан список
        log_user_action(
            db_session,
            telegram_id,
            "/unsubscribe",
            f"Displaying {len(subscriptions)} subscriptions for cancellation",
        )


@dp.callback_query(F.data.startswith("unsubscribe_confirm:"))
async def process_unsubscribe_confirm(
    callback_query: types.CallbackQuery, state: FSMContext
):  # state для единообразия
    """
    Обрабатывает подтверждение отписки (нажатие на кнопку с подпиской).
    Деактивирует выбранную подписку.
    """
    await callback_query.answer()  # Снимаем "часики" с кнопки
    subscription_id_to_delete: int = int(callback_query.data.split(":")[1])
    telegram_id: int = callback_query.from_user.id
    log_details: str = f"Subscription ID to delete: {subscription_id_to_delete}"

    with get_session() as db_session:
        db_user = get_user_by_telegram_id(session=db_session, telegram_id=telegram_id)
        if not db_user:
            await callback_query.message.edit_text("Ошибка: пользователь не найден.")
            log_user_action(
                db_session,
                telegram_id,
                "unsubscribe_error",
                f"{log_details}, user_not_found",
            )
            return

        subscription_to_check: Optional[Subscription] = db_session.get(
            Subscription, subscription_id_to_delete
        )
        if not subscription_to_check or subscription_to_check.user_id != db_user.id:
            await callback_query.message.edit_text(
                "Ошибка: это не ваша подписка или она не найдена."
            )
            log_user_action(
                db_session,
                telegram_id,
                "unsubscribe_error",
                f"{log_details}, sub_not_found_or_not_owner",
            )
            return

        success: bool = delete_subscription(
            session=db_session, subscription_id=subscription_id_to_delete
        )
        if success:
            await callback_query.message.edit_text("Вы успешно отписались.")
            log_user_action(
                db_session, telegram_id, "unsubscribe_confirm_success", log_details
            )
        else:  # Этот случай маловероятен, если проверки выше прошли
            await callback_query.message.edit_text("Не удалось отписаться...")
            log_user_action(
                db_session, telegram_id, "unsubscribe_confirm_fail", log_details
            )


@dp.callback_query(F.data == "unsubscribe_action_cancel")
async def process_unsubscribe_action_cancel(
    callback_query: types.CallbackQuery, state: FSMContext
):  # state для единообразия
    """
    Обрабатывает нажатие кнопки "Отменить операцию" в диалоге отписки.
    """
    telegram_id: int = callback_query.from_user.id
    with get_session() as db_session:
        log_user_action(db_session, telegram_id, "unsubscribe_action_cancel")
    await callback_query.answer()
    await callback_query.message.edit_text("Операция отписки отменена.")


# --- ФУНКЦИИ ЖИЗНЕННОГО ЦИКЛА БОТА И ПЛАНИРОВЩИКА ---
async def on_startup():
    """
    Выполняется при запуске бота.
    Создает таблицы БД, настраивает команды меню и запускает планировщик.
    """
    logger.info("Бот запускается...")
    create_db_and_tables()  # Создаем таблицы, если их нет

    # Импортируем здесь, чтобы избежать циклических зависимостей на уровне модуля,
    # если этот файл импортируется где-то еще до полной инициализации scheduler.main
    from app.scheduler.main import (
        set_bot_instance,
        schedule_jobs,
        scheduler as aps_scheduler,
    )

    set_bot_instance(bot)  # Передаем экземпляр бота в модуль планировщика
    schedule_jobs()  # Добавляем задачи в планировщик

    # Запускаем планировщик, если он еще не запущен
    if not aps_scheduler.running:
        try:
            aps_scheduler.start()
            logger.info("Планировщик APScheduler успешно запущен из on_startup.")
        except Exception as e:
            logger.error(
                f"Ошибка при запуске планировщика из on_startup: {e}", exc_info=True
            )
    else:
        logger.info(
            "Планировщик APScheduler уже был запущен (возможно, при предыдущем запуске on_startup)."
        )

    # Установка команд меню бота
    commands_to_set = [
        types.BotCommand(command="start", description="🚀 Запуск и регистрация"),
        types.BotCommand(command="help", description="❓ Помощь по командам"),
        types.BotCommand(command="weather", description="☀️ Узнать погоду (город)"),
        types.BotCommand(command="news", description="📰 Последние новости (Россия)"),
        types.BotCommand(command="events", description="🎉 События (город)"),
        types.BotCommand(command="subscribe", description="🔔 Подписаться на рассылку"),
        types.BotCommand(command="mysubscriptions", description="📜 Мои подписки"),
        types.BotCommand(
            command="unsubscribe", description="🔕 Отписаться от рассылки"
        ),
        types.BotCommand(command="cancel", description="❌ Отменить текущее действие"),
    ]
    try:
        await bot.set_my_commands(commands_to_set)
        logger.info("Команды бота успешно установлены в меню Telegram.")
    except Exception as e:
        logger.error(f"Ошибка при установке команд бота: {e}", exc_info=True)
    logger.info("Бот успешно запущен!")


async def on_shutdown_local():  # Переименовал, чтобы не конфликтовать с импортируемым shutdown_scheduler
    """
    Выполняется при остановке бота (локальные действия).
    """
    logger.info("Бот останавливается (локальный on_shutdown)...")
    # Здесь можно добавить специфичные для бота действия при остановке, если они нужны,
    # кроме остановки планировщика, которая обрабатывается отдельно.
    logger.info("Бот остановлен (локальный on_shutdown).")


# Главная точка входа для запуска бота
if __name__ == "__main__":
    # Импортируем shutdown_scheduler здесь, чтобы он был доступен для регистрации
    from app.scheduler.main import shutdown_scheduler

    # Регистрируем обработчики жизненного цикла
    dp.startup.register(on_startup)
    dp.shutdown.register(
        shutdown_scheduler
    )  # Остановка планировщика при выключении бота
    dp.shutdown.register(on_shutdown_local)  # Локальные действия при выключении бота

    # Запускаем поллинг бота
    asyncio.run(dp.start_polling(bot, skip_updates=True))
