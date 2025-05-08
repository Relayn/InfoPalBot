import logging
import asyncio
import html # Для экранирования HTML
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from app.config import settings
from app.database.session import get_session, create_db_and_tables
from app.database.crud import create_user_if_not_exists
from app.api_clients.weather import get_weather_data
from app.api_clients.news import get_top_headlines # Используем get_top_headlines

# Настройка логирования
logging.basicConfig(level=settings.LOG_LEVEL,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация бота
default_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=default_properties)

# Инициализация диспетчера
dp = Dispatcher()

# Обработчик команды /start
@dp.message(Command('start'))
async def process_start_command(message: types.Message):
    """
    Обработчик команды /start.
    Отвечает на команду приветственным сообщением и регистрирует пользователя.
    """
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

# Обработчик команды /help
@dp.message(Command('help'))
async def process_help_command(message: types.Message):
    """
    Обработчик команды /help.
    Отправляет пользователю список доступных команд.
    """
    help_text = (
        "<b>Доступные команды:</b>\n"
        "<code>/start</code> - Начать работу с ботом и зарегистрироваться\n"
        "<code>/help</code> - Показать это сообщение со справкой\n"
        "<code>/weather [город]</code> - Получить текущий прогноз погоды (например, <code>/weather Москва</code>)\n"
        "<code>/news</code> - Получить последние новости (Россия)\n" # Обновлено описание /news
        "<code>/events</code> - Узнать о предстоящих событиях (в разработке)\n"
        "\n"
        "<b>Подписки (в разработке):</b>\n"
        "<code>/subscribe</code> - Подписаться на рассылку\n"
        "<code>/unsubscribe</code> - Отписаться от рассылки\n"
        "<code>/mysubscriptions</code> - Посмотреть мои подписки\n"
    )
    await message.answer(help_text)
    logger.info(f"Отправлена справка по команде /help пользователю {message.from_user.id}")

# Обработчик команды /weather
@dp.message(Command('weather'))
async def process_weather_command(message: types.Message, command: CommandObject):
    """
    Обработчик команды /weather.
    Запрашивает погоду для указанного города.
    """
    city_name = command.args
    user_id = message.from_user.id

    if not city_name:
        await message.reply("Пожалуйста, укажите название города после команды /weather.\n"
                            "Например: <code>/weather Москва</code>")
        logger.info(f"Команда /weather вызвана без указания города пользователем {user_id}.")
        return

    logger.info(f"Пользователь {user_id} запросил погоду для города: {city_name}")
    await message.reply(f"Запрашиваю погоду для города <b>{city_name}</b>...")

    weather_data = await get_weather_data(city_name.strip())

    if weather_data and not weather_data.get("error"):
        try:
            description = weather_data['weather'][0]['description'].capitalize()
            temp = weather_data['main']['temp']
            feels_like = weather_data['main']['feels_like']
            humidity = weather_data['main']['humidity']
            wind_speed = weather_data['wind']['speed']
            wind_deg = weather_data['wind'].get('deg')
            wind_direction_str = ""
            if wind_deg is not None:
                directions = ["Северный", "С-В", "Восточный", "Ю-В", "Южный", "Ю-З", "Западный", "С-З"]
                wind_direction_str = f", {directions[int((wind_deg % 360) / 45)]}"

            response_text = (
                f"<b>Погода в городе {weather_data.get('name', city_name)}:</b>\n"
                f"🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n"
                f"💧 Влажность: {humidity}%\n"
                f"💨 Ветер: {wind_speed} м/с{wind_direction_str}\n"
                f"☀️ Описание: {description}"
            )
            await message.answer(response_text)
            logger.info(f"Успешно отправлена погода для города {city_name} пользователю {user_id}.")
        except KeyError as e:
            logger.error(f"Ошибка парсинга данных о погоде для города {city_name}: отсутствует ключ {e}. Данные: {weather_data}", exc_info=True)
            await message.answer("Не удалось обработать данные о погоде. Попробуйте другой город или повторите попытку позже.")
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при формировании ответа о погоде для {city_name}: {e}", exc_info=True)
            await message.answer("Произошла ошибка при отображении погоды.")

    elif weather_data and weather_data.get("error"):
        error_message = weather_data.get("message", "Неизвестная ошибка от сервиса погоды.")
        status_code = weather_data.get("status_code")
        if status_code == 404:
            await message.reply(f"Город <b>{city_name}</b> не найден. Пожалуйста, проверьте название и попробуйте снова.")
        elif status_code == 401:
             await message.reply("Проблема с доступом к сервису погоды (неверный API ключ). Администратор уведомлен.")
             logger.critical("API ключ для OpenWeatherMap недействителен или неверно настроен!")
        else:
            await message.reply(f"Не удалось получить погоду: {error_message}")
        logger.warning(f"Ошибка от API погоды для города {city_name} (пользователь {user_id}): {error_message}")
    else:
        await message.reply("Не удалось получить данные о погоде. Пожалуйста, попробуйте позже.")
        logger.error(f"get_weather_data вернул None или неожиданный результат для города {city_name} (пользователь {user_id}).")

# Обработчик команды /news
@dp.message(Command('news'))
async def process_news_command(message: types.Message):
    """
    Обработчик команды /news.
    Запрашивает главные новости для России.
    """
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} запросил новости.")
    await message.reply("Запрашиваю последние главные новости для России...")

    articles_or_error = await get_top_headlines(country="ru", page_size=5)

    if isinstance(articles_or_error, list) and articles_or_error:
        response_lines = ["<b>📰 Последние главные новости (Россия):</b>"]
        for i, article in enumerate(articles_or_error):
            title = article.get('title', 'Без заголовка')
            url = article.get('url', '#')
            source = article.get('source', {}).get('name', 'Неизвестный источник')
            # Используем html.escape для экранирования
            title = html.escape(title)
            response_lines.append(f"{i+1}. <a href='{url}'>{title}</a> ({source})")

        response_text = "\n".join(response_lines)
        await message.answer(response_text, disable_web_page_preview=True)
        logger.info(f"Успешно отправлены новости пользователю {user_id}.")

    elif isinstance(articles_or_error, list) and not articles_or_error:
        await message.reply("На данный момент нет главных новостей для отображения.")
        logger.info(f"Главных новостей для России не найдено (пользователь {user_id}).")

    elif isinstance(articles_or_error, dict) and articles_or_error.get("error"):
        error_message = articles_or_error.get("message", "Неизвестная ошибка от сервиса новостей.")
        await message.reply(f"Не удалось получить новости: {error_message}")
        logger.warning(f"Ошибка от API новостей (пользователь {user_id}): {error_message}")
    else:
        await message.reply("Не удалось получить данные о новостях. Пожалуйста, попробуйте позже.")
        logger.error(f"get_top_headlines вернул неожиданный результат для России (пользователь {user_id}): {articles_or_error}")


# TODO: Добавить обработчик команды /events

# TODO: Добавить обработчики для подписок

# Функция, которая будет выполняться при запуске бота
async def on_startup(bot: Bot):
    """
    Действия, выполняемые при запуске бота.
    """
    logger.info("Бот запускается...")
    create_db_and_tables()
    commands_to_set = [
        types.BotCommand(command="start", description="🚀 Запуск и регистрация"),
        types.BotCommand(command="help", description="❓ Помощь по командам"),
        types.BotCommand(command="weather", description="☀️ Узнать погоду (город)"),
        types.BotCommand(command="news", description="📰 Последние новости (Россия)"),
        types.BotCommand(command="events", description="🎉 Предстоящие события"),
    ]
    try:
        await bot.set_my_commands(commands_to_set)
        logger.info("Команды бота успешно установлены в меню Telegram.")
    except Exception as e:
        logger.error(f"Ошибка при установке команд бота: {e}")
    logger.info("Бот успешно запущен!")

# Функция, которая будет выполняться при остановке бота
async def on_shutdown(bot: Bot):
    """
    Действия, выполняемые при остановке бота.
    """
    logger.info("Бот останавливается...")
    logger.info("Бот остановлен.")

# Главная точка входа для запуска бота в режиме long-polling
if __name__ == '__main__':
    asyncio.run(dp.start_polling(
        bot,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    ))