import logging
import asyncio
import html
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

from app.config import settings
from app.database.session import get_session, create_db_and_tables
from app.database.models import User, Subscription, Log
from app.database.crud import (
    create_user_if_not_exists,
    create_subscription,
    get_subscriptions_by_user_id,
    get_subscription_by_user_and_type,
    delete_subscription,
    get_user_by_telegram_id
)
from app.api_clients.weather import get_weather_data
from app.api_clients.news import get_top_headlines
from app.api_clients.events import get_kudago_events

# Настройка логирования
logging.basicConfig(level=settings.LOG_LEVEL,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация бота
default_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=default_properties)

# Инициализация диспетчера
dp = Dispatcher()

# Словарь для сопоставления названий городов и кодов KudaGo
KUDAGO_LOCATION_SLUGS = {
    "москва": "msk", "мск": "msk", "moscow": "msk",
    "санкт-петербург": "spb", "спб": "spb", "питер": "spb", "saint petersburg": "spb",
    "новосибирск": "nsk", "нск": "nsk",
    "екатеринбург": "ekb", "екб": "ekb",
    "казань": "kzn",
    "нижний новгород": "nnv",
}

# --- Определяем состояния FSM для подписки ---
class SubscriptionStates(StatesGroup):
    choosing_info_type = State()
    entering_city_weather = State()
    entering_city_events = State()

# --- Обработчики команд ---

# Команда /cancel (срабатывает в любом состоянии FSM или без него)
@dp.message(Command('cancel'), StateFilter('*')) # StateFilter('*') - любое состояние, включая None
async def cmd_cancel_any_state(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активного действия для отмены.", reply_markup=ReplyKeyboardRemove())
        return
    logger.info(f"Пользователь {message.from_user.id} отменил действие командой /cancel из состояния {current_state}.")
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=ReplyKeyboardRemove())


@dp.message(Command('start'), StateFilter('*')) # Добавил StateFilter('*') чтобы /start тоже сбрасывал состояние
async def process_start_command(message: types.Message, state: FSMContext):
    """
    Обработчик команды /start.
    Отвечает на команду приветственным сообщением и регистрирует пользователя.
    Также сбрасывает любое активное состояние FSM.
    """
    logger.info(f"Команда /start вызвана пользователем {message.from_user.id}. Текущее состояние: {await state.get_state()}")
    await state.clear() # Сбрасываем состояние FSM, если оно было
    telegram_id = message.from_user.id
    try:
        with next(get_session()) as session:
            user = create_user_if_not_exists(session=session, telegram_id=telegram_id)
            logger.info(f"Обработана команда /start от пользователя {telegram_id}. Пользователь в БД: {user.id}")
        await message.answer(f"Привет, {message.from_user.full_name}! Я InfoPalBot. Я могу предоставить тебе актуальную информацию.\n"
                             f"Используй /help, чтобы увидеть список доступных команд.")
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /start для пользователя {telegram_id}: {e}", exc_info=True)
        await message.answer("Произошла ошибка при обработке вашего запроса. Попробуйте позже.")


@dp.message(Command('help'))
async def process_help_command(message: types.Message):
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
    logger.info(f"Отправлена справка по команде /help пользователю {message.from_user.id}")


@dp.message(Command('weather'))
async def process_weather_command(message: types.Message, command: CommandObject):
    city_name = command.args
    user_id = message.from_user.id
    if not city_name:
        await message.reply("Пожалуйста, укажите название города...")
        return
    logger.info(f"Пользователь {user_id} запросил погоду для города: {city_name}")
    await message.reply(f"Запрашиваю погоду для города <b>{html.escape(city_name)}</b>...")
    weather_data = await get_weather_data(city_name.strip())
    if weather_data and not weather_data.get("error"):
        try:
            description = weather_data['weather'][0]['description'].capitalize(); temp = weather_data['main']['temp']
            feels_like = weather_data['main']['feels_like']; humidity = weather_data['main']['humidity']
            wind_speed = weather_data['wind']['speed']; wind_deg = weather_data['wind'].get('deg')
            wind_direction_str = ""
            if wind_deg is not None:
                directions = ["Северный", "С-В", "Восточный", "Ю-В", "Южный", "Ю-З", "Западный", "С-З"]
                wind_direction_str = f", {directions[int((wind_deg % 360) / 45)]}"
            response_text = (
                f"<b>Погода в городе {html.escape(weather_data.get('name', city_name))}:</b>\n"
                f"🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n💧 Влажность: {humidity}%\n"
                f"💨 Ветер: {wind_speed} м/с{wind_direction_str}\n☀️ Описание: {description}"
            )
            await message.answer(response_text)
        except Exception: await message.answer("Не удалось обработать данные о погоде...")
    elif weather_data and weather_data.get("error"): await message.reply(f"Не удалось получить погоду: {html.escape(weather_data.get('message', 'Ошибка'))}")
    else: await message.reply("Не удалось получить данные о погоде...")


@dp.message(Command('news'))
async def process_news_command(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} запросил новости.")
    await message.reply("Запрашиваю последние главные новости для России...")
    articles_or_error = await get_top_headlines(country="ru", page_size=5)
    if isinstance(articles_or_error, list) and articles_or_error:
        response_lines = ["<b>📰 Последние главные новости (Россия):</b>"]
        for i, article in enumerate(articles_or_error):
            title = html.escape(article.get('title', 'Без заголовка')); url = article.get('url', '#')
            source = article.get('source', {}).get('name', 'Неизвестный источник')
            response_lines.append(f"{i+1}. <a href='{url}'>{title}</a> ({source})")
        await message.answer("\n".join(response_lines), disable_web_page_preview=True)
    elif isinstance(articles_or_error, list): await message.reply("На данный момент нет главных новостей...")
    elif isinstance(articles_or_error, dict) and articles_or_error.get("error"): await message.reply(f"Не удалось получить новости: {html.escape(articles_or_error.get('message', 'Ошибка'))}")
    else: await message.reply("Не удалось получить данные о новостях...")


@dp.message(Command('events'))
async def process_events_command(message: types.Message, command: CommandObject):
    city_arg = command.args; user_id = message.from_user.id
    if not city_arg: await message.reply("Пожалуйста, укажите город...\nДоступные города: Москва, Санкт-Петербург..."); return
    location_slug = KUDAGO_LOCATION_SLUGS.get(city_arg.strip().lower())
    if not location_slug: await message.reply(f"К сожалению, не знаю событий для города '{html.escape(city_arg)}'...\nПопробуйте: Москва, Санкт-Петербург..."); return
    await message.reply(f"Запрашиваю актуальные события для города <b>{html.escape(city_arg)}</b>...")
    events_result = await get_kudago_events(location=location_slug, page_size=5)
    if isinstance(events_result, list) and events_result:
        response_lines = [f"<b>🎉 Актуальные события в городе {html.escape(city_arg.capitalize())}:</b>"]
        for i, event in enumerate(events_result):
            title = html.escape(event.get('title', 'Без заголовка')); site_url = event.get('site_url', '#')
            description_raw = event.get('description', ''); description = html.unescape(description_raw.replace('<p>', '').replace('</p>', '').replace('<br>', '\n')).strip()
            event_str = f"{i+1}. <a href='{site_url}'>{title}</a>"
            if description:
                max_desc_len = 100
                if len(description) > max_desc_len: description = description[:max_desc_len] + "..."
                event_str += f"\n   <i>{html.escape(description)}</i>"
            response_lines.append(event_str)
        await message.answer("\n\n".join(response_lines), disable_web_page_preview=True)
    elif isinstance(events_result, list): await message.reply(f"Не найдено актуальных событий для города <b>{html.escape(city_arg)}</b>.")
    elif isinstance(events_result, dict) and events_result.get("error"): await message.reply(f"Не удалось получить события: {html.escape(events_result.get('message', 'Ошибка'))}")
    else: await message.reply("Не удалось получить данные о событиях...")


# --- Обработчики для /subscribe и FSM ---

INFO_TYPE_WEATHER = "weather"
INFO_TYPE_NEWS = "news"
INFO_TYPE_EVENTS = "events"

@dp.message(Command('subscribe'), StateFilter(None))
async def process_subscribe_command_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} начал процесс подписки командой /subscribe.")
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
    selected_type = callback_query.data.split(":")[1]; user_id = callback_query.from_user.id
    logger.info(f"Пользователь {user_id} выбрал тип информации для подписки: {selected_type}")
    await state.update_data(info_type=selected_type)
    if selected_type == INFO_TYPE_WEATHER:
        await callback_query.message.edit_text("Вы выбрали 'Погода'.\nПожалуйста, введите название города...")
        await state.set_state(SubscriptionStates.entering_city_weather)
    elif selected_type == INFO_TYPE_EVENTS:
        await callback_query.message.edit_text("Вы выбрали 'События'.\nПожалуйста, введите название города (например, Москва, спб).")
        await state.set_state(SubscriptionStates.entering_city_events)
    elif selected_type == INFO_TYPE_NEWS:
        frequency = "daily"; user_id = callback_query.from_user.id
        with next(get_session()) as db_session:
            db_user = create_user_if_not_exists(db_session, user_id)
            existing_subscription = get_subscription_by_user_and_type(db_session, db_user.id, INFO_TYPE_NEWS)
            if existing_subscription: await callback_query.message.edit_text("Вы уже подписаны на 'Новости (Россия)'.")
            else:
                create_subscription(db_session, db_user.id, INFO_TYPE_NEWS, frequency)
                await callback_query.message.edit_text(f"Вы успешно подписались на 'Новости (Россия)' с частотой '{frequency}'.")
        await state.clear()

@dp.callback_query(StateFilter(SubscriptionStates.choosing_info_type), F.data == "subscribe_fsm_cancel")
async def callback_fsm_cancel_process(callback_query: types.CallbackQuery, state: FSMContext):
    logger.info(f"Пользователь {callback_query.from_user.id} отменил процесс подписки кнопкой 'Отмена'.")
    await callback_query.answer()
    await callback_query.message.edit_text("Процесс подписки отменен.")
    await state.clear()

@dp.message(StateFilter(SubscriptionStates.entering_city_weather), F.text)
async def process_city_for_weather_subscription(message: types.Message, state: FSMContext):
    city_name = message.text.strip(); user_id = message.from_user.id
    user_data = await state.get_data(); info_type = user_data.get("info_type")
    if not city_name: await message.reply("Название города не может быть пустым..."); return
    logger.info(f"Пользователь {user_id} ввел город '{city_name}' для подписки на '{info_type}'.")
    frequency = "daily"
    with next(get_session()) as db_session:
        db_user = create_user_if_not_exists(db_session, user_id)
        existing_subscription = get_subscription_by_user_and_type(db_session, db_user.id, info_type, city_name)
        if existing_subscription: await message.answer(f"Вы уже подписаны на '{info_type}' для города '{html.escape(city_name)}'.")
        else:
            create_subscription(db_session, db_user.id, info_type, frequency, city_name)
            await message.answer(f"Вы успешно подписались на '{info_type}' для города '{html.escape(city_name)}' с частотой '{frequency}'.")
    await state.clear()

@dp.message(StateFilter(SubscriptionStates.entering_city_events), F.text)
async def process_city_for_events_subscription(message: types.Message, state: FSMContext):
    city_arg = message.text.strip(); user_id = message.from_user.id
    user_data = await state.get_data(); info_type = user_data.get("info_type")
    if not city_arg: await message.reply("Название города не может быть пустым..."); return
    location_slug = KUDAGO_LOCATION_SLUGS.get(city_arg.lower())
    if not location_slug:
        await message.reply(f"К сожалению, не знаю событий для города '{html.escape(city_arg)}'...\nПопробуйте: Москва, Санкт-Петербург...")
        return # Остаемся в состоянии
    logger.info(f"Пользователь {user_id} ввел город '{city_arg}' (slug: {location_slug}) для подписки на '{info_type}'.")
    frequency = "daily"
    with next(get_session()) as db_session:
        db_user = create_user_if_not_exists(db_session, user_id)
        existing_subscription = get_subscription_by_user_and_type(db_session, db_user.id, info_type, location_slug)
        if existing_subscription: await message.answer(f"Вы уже подписаны на '{info_type}' для города '{html.escape(city_arg)}'.")
        else:
            create_subscription(db_session, db_user.id, info_type, frequency, location_slug)
            await message.answer(f"Вы успешно подписались на '{info_type}' для города '{html.escape(city_arg)}' с частотой '{frequency}'.")
    await state.clear()

# --- Новые обработчики для управления подписками ---

@dp.message(Command('mysubscriptions'))
async def process_mysubscriptions_command(message: types.Message):
    """
    Обработчик команды /mysubscriptions.
    Показывает пользователю его активные подписки.
    """
    user_id_telegram = message.from_user.id
    logger.info(f"Пользователь {user_id_telegram} запросил список своих подписок командой /mysubscriptions.")

    with next(get_session()) as db_session:
        # Сначала получаем нашего пользователя из БД, чтобы получить его внутренний ID
        db_user = get_user_by_telegram_id(session=db_session, telegram_id=user_id_telegram)

        if not db_user:
            # Этого не должно произойти, если /start всегда вызывается первым,
            # но на всякий случай проверяем.
            await message.answer("Не удалось найти информацию о вас. Пожалуйста, выполните /start.")
            logger.warning(f"Не найден пользователь с telegram_id {user_id_telegram} при запросе /mysubscriptions.")
            return

        # Получаем все активные подписки пользователя
        subscriptions = get_subscriptions_by_user_id(session=db_session, user_id=db_user.id)

        if not subscriptions:
            await message.answer("У вас пока нет активных подписок.\n"
                                 "Вы можете подписаться с помощью команды /subscribe.")
            logger.info(f"У пользователя {user_id_telegram} (DB ID: {db_user.id}) нет активных подписок.")
            return

        response_lines = ["<b>📋 Ваши активные подписки:</b>"]
        for i, sub in enumerate(subscriptions):
            sub_details_str = ""
            if sub.info_type == INFO_TYPE_WEATHER:
                sub_details_str = f"Погода для города: <b>{html.escape(sub.details or 'Не указан')}</b>"
            elif sub.info_type == INFO_TYPE_NEWS:
                sub_details_str = "Новости (Россия)"
            elif sub.info_type == INFO_TYPE_EVENTS:
                # Пытаемся найти название города по slug'у для красивого отображения
                city_display_name = sub.details # По умолчанию slug
                for name, slug_val in KUDAGO_LOCATION_SLUGS.items():
                    if slug_val == sub.details:
                        city_display_name = name.capitalize()
                        break
                sub_details_str = f"События в городе: <b>{html.escape(city_display_name)}</b>"
            else:
                sub_details_str = f"Тип: {html.escape(sub.info_type)}"
                if sub.details:
                    sub_details_str += f", Детали: {html.escape(sub.details)}"

            frequency_str = f"(Частота: {html.escape(sub.frequency or 'не указана')})"
            # Пока не добавляем кнопку отписки, сделаем это с командой /unsubscribe
            response_lines.append(f"{i+1}. {sub_details_str} {frequency_str}")

        response_text = "\n".join(response_lines)
        await message.answer(response_text)
        logger.info(f"Пользователю {user_id_telegram} (DB ID: {db_user.id}) отправлен список из {len(subscriptions)} подписок.")


@dp.message(Command('unsubscribe'))
async def process_unsubscribe_command_start(message: types.Message,
                                            state: FSMContext):  # Добавляем state, т.к. это может стать FSM
    """
    Начинает процесс отписки. Показывает список активных подписок с кнопками для отмены.
    """
    user_id_telegram = message.from_user.id
    logger.info(f"Пользователь {user_id_telegram} начал процесс отписки командой /unsubscribe.")

    with next(get_session()) as db_session:
        db_user = get_user_by_telegram_id(session=db_session, telegram_id=user_id_telegram)
        if not db_user:
            await message.answer("Не удалось найти информацию о вас. Пожалуйста, выполните /start.")
            return

        subscriptions = get_subscriptions_by_user_id(session=db_session, user_id=db_user.id)

        if not subscriptions:
            await message.answer("У вас нет активных подписок для отмены.")
            return

        keyboard_buttons = []
        for sub in subscriptions:
            sub_details_str = ""
            if sub.info_type == INFO_TYPE_WEATHER:
                sub_details_str = f"Погода: {html.escape(sub.details or 'Город не указан')}"
            elif sub.info_type == INFO_TYPE_NEWS:
                sub_details_str = "Новости (Россия)"
            elif sub.info_type == INFO_TYPE_EVENTS:
                city_display_name = sub.details
                for name, slug_val in KUDAGO_LOCATION_SLUGS.items():
                    if slug_val == sub.details: city_display_name = name.capitalize(); break
                sub_details_str = f"События: {html.escape(city_display_name)}"
            else:
                sub_details_str = f"{html.escape(sub.info_type)}"
                if sub.details: sub_details_str += f", {html.escape(sub.details)}"

            # callback_data будет содержать ID подписки для ее удаления
            keyboard_buttons.append(
                [InlineKeyboardButton(text=f"❌ {sub_details_str} (ежедн.)",  # Пока частота 'ежедн.' захардкожена
                                      callback_data=f"unsubscribe_confirm:{sub.id}")]
            )

        if not keyboard_buttons:  # На всякий случай, если после фильтрации ничего не осталось
            await message.answer("Не удалось сформировать список подписок для отмены.")
            return

        keyboard_buttons.append(
            [InlineKeyboardButton(text="Отменить операцию", callback_data="unsubscribe_action_cancel")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await message.answer("Выберите подписку, от которой хотите отписаться:", reply_markup=keyboard)
        # Пока не устанавливаем состояние FSM, сделаем это на следующем шаге для подтверждения


# Callback-обработчик для подтверждения отписки (пока просто деактивирует)
@dp.callback_query(F.data.startswith("unsubscribe_confirm:"))
async def process_unsubscribe_confirm(callback_query: types.CallbackQuery, state: FSMContext):  # Добавили state
    """
    Обрабатывает нажатие на кнопку отписки. Деактивирует подписку.
    """
    await callback_query.answer()  # Отвечаем на callback
    subscription_id_to_delete = int(callback_query.data.split(":")[1])
    user_id_telegram = callback_query.from_user.id

    logger.info(f"Пользователь {user_id_telegram} выбрал для отписки ID: {subscription_id_to_delete}")

    with next(get_session()) as db_session:
        # Дополнительная проверка: принадлежит ли эта подписка пользователю?
        db_user = get_user_by_telegram_id(session=db_session, telegram_id=user_id_telegram)
        if not db_user:
            await callback_query.message.edit_text("Ошибка: пользователь не найден.")
            return

        subscription_to_check = db_session.get(Subscription, subscription_id_to_delete)
        if not subscription_to_check or subscription_to_check.user_id != db_user.id:
            await callback_query.message.edit_text("Ошибка: это не ваша подписка или она не найдена.")
            logger.warning(
                f"Попытка отписки от чужой/несуществующей подписки ID {subscription_id_to_delete} пользователем {user_id_telegram}")
            return

        success = delete_subscription(session=db_session, subscription_id=subscription_id_to_delete)

        if success:
            await callback_query.message.edit_text("Вы успешно отписались.")
            logger.info(
                f"Пользователь {user_id_telegram} успешно отписался от подписки ID {subscription_id_to_delete}.")
        else:
            # Эта ветка маловероятна, если проверка выше прошла, но на всякий случай
            await callback_query.message.edit_text("Не удалось отписаться. Возможно, подписка уже была удалена.")
            logger.warning(
                f"Не удалось отписать пользователя {user_id_telegram} от подписки ID {subscription_id_to_delete} (delete_subscription вернул False).")

    # Если бы это был FSM, здесь бы был state.clear()


# Callback-обработчик для кнопки "Отменить операцию" в /unsubscribe
@dp.callback_query(F.data == "unsubscribe_action_cancel")
async def process_unsubscribe_action_cancel(callback_query: types.CallbackQuery, state: FSMContext):  # Добавили state
    await callback_query.answer()
    await callback_query.message.edit_text("Операция отписки отменена.")
    logger.info(f"Пользователь {callback_query.from_user.id} отменил операцию отписки.")

# --- Функции жизненного цикла бота ---
async def on_startup():
    logger.info("Бот запускается...")
    create_db_and_tables()
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
    logger.info("Бот остановлен.")

# Главная точка входа для запуска бота
if __name__ == '__main__':
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    asyncio.run(dp.start_polling(bot, skip_updates=True))