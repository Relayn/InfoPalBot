"""
Модуль, содержащий асинхронные задачи, которые будут выполняться планировщиком APScheduler.
Эти задачи отвечают за получение данных из внешних API и рассылку уведомлений подписчикам.

Этот модуль реализует следующие задачи:
1. Тестовая задача для проверки работы планировщика
2. Рассылка прогнозов погоды подписчикам
3. Рассылка свежих новостей подписчикам
4. Рассылка актуальных событий из KudaGo подписчикам

Каждая задача:
- Получает список активных подписок из базы данных
- Запрашивает данные из соответствующих API
- Форматирует сообщения с учетом HTML-разметки
- Отправляет уведомления подписчикам
- Логирует все действия и ошибки

Особенности реализации:
- Асинхронное выполнение всех операций
- Обработка ошибок на всех этапах
- Кэширование данных для оптимизации запросов
- Группировка подписчиков для минимизации дублирования
- Безопасная работа с HTML-разметкой

Пример использования:
    # В main.py или другом модуле:
    scheduler.add_job(send_weather_updates, 'interval', hours=3, args=[bot])
    scheduler.add_job(send_news_updates, 'interval', hours=6, args=[bot])
    scheduler.add_job(send_events_updates, 'interval', minutes=2, args=[bot])
"""

import logging
from datetime import datetime
from aiogram import Bot  # Для передачи экземпляра бота в задачи рассылки
from aiogram.enums import ParseMode  # Для явного указания parse_mode в send_message
import html  # Для экранирования HTML-сущностей в сообщениях
from typing import List, Dict, Any, Optional  # Для аннотаций типов

# Импортируем необходимые функции для работы с БД
from app.database.session import get_session
from app.database.crud import get_active_subscriptions_by_info_type

# Импортируем модели для работы с объектами БД
from app.database.models import (
    User,
    Subscription,
)  # Subscription используется в type hinting

# Импортируем API-клиенты для получения данных
from app.api_clients.weather import get_weather_data
from app.api_clients.news import get_top_headlines
from app.api_clients.events import get_kudago_events

# Импортируем константы для типов информации и кодов городов
from app.bot.constants import (
    INFO_TYPE_WEATHER,
    INFO_TYPE_NEWS,
    INFO_TYPE_EVENTS,
    KUDAGO_LOCATION_SLUGS,
)

# Настройка логгера для модуля
logger = logging.getLogger(__name__)


async def test_scheduled_task() -> None:
    """
    Простая тестовая задача, которая выполняется по расписанию для проверки работы планировщика.

    Эта задача:
    1. Получает текущее время
    2. Логирует информацию о своем выполнении

    Note:
        - Задача выполняется каждые 30 секунд
        - Используется для проверки работоспособности планировщика
        - Не требует доступа к базе данных или внешним API
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"APScheduler: Тестовая задача выполнена в {current_time}!")


async def send_weather_updates(bot: Bot) -> None:
    """
    Задача для рассылки обновлений погоды подписчикам.
    Получает активные подписки на погоду, запрашивает данные и отправляет уведомления.

    Процесс работы:
    1. Получение списка активных подписок на погоду
    2. Для каждой подписки:
       - Проверка наличия необходимых данных (город, user_id)
       - Получение данных пользователя из БД
       - Запрос погоды через API
       - Форматирование и отправка сообщения
    3. Логирование результатов

    Args:
        bot (Bot): Экземпляр бота Aiogram для отправки сообщений.

    Note:
        - Задача выполняется каждые 3 часа
        - Сообщения форматируются с использованием HTML
        - Обрабатываются все возможные ошибки (API, БД, отправка)
        - Пропускаются некорректные подписки
        - Температура возвращается в градусах Цельсия
    """
    logger.info("APScheduler: Запуск задачи send_weather_updates...")
    with get_session() as db_session:  # Используем контекстный менеджер для сессии БД
        # Получаем все активные подписки на погоду
        weather_subscriptions: List[Subscription] = (
            get_active_subscriptions_by_info_type(
                session=db_session, info_type=INFO_TYPE_WEATHER
            )
        )
        logger.info(
            f"Найдено {len(weather_subscriptions)} активных подписок на погоду."
        )

        for sub in weather_subscriptions:
            # Пропускаем подписки без необходимых деталей или user_id
            if not sub.details or not sub.user_id:
                logger.warning(
                    f"Пропуск подписки ID {sub.id}: отсутствует город (details) или user_id."
                )
                continue

            # Получаем объект пользователя из БД, чтобы получить его Telegram ID
            user: Optional[User] = db_session.get(User, sub.user_id)
            if not user or not user.telegram_id:
                logger.warning(
                    f"Не найден пользователь или telegram_id для подписки ID {sub.id} (user_id: {sub.user_id})."
                )
                continue

            telegram_id_to_send: int = user.telegram_id
            city_name: str = sub.details

            logger.info(
                f"Обработка подписки на погоду для пользователя {telegram_id_to_send}, город: {city_name}"
            )
            # Получаем данные о погоде через API клиент
            weather_data: Optional[Dict[str, Any]] = await get_weather_data(city_name)

            if weather_data and not weather_data.get("error"):
                try:
                    # Форматируем сообщение о погоде
                    description: str = weather_data["weather"][0][
                        "description"
                    ].capitalize()
                    temp: float = weather_data["main"]["temp"]
                    feels_like: float = weather_data["main"]["feels_like"]
                    # Формируем текст сообщения
                    message_text: str = (
                        f"🔔 <b>Ежедневный прогноз погоды для г. {html.escape(city_name)}:</b>\n"
                        f"🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n"
                        f"☀️ Описание: {description}"
                    )
                    # Отправляем сообщение пользователю
                    await bot.send_message(
                        chat_id=telegram_id_to_send,
                        text=message_text,
                        parse_mode=ParseMode.HTML,
                    )  # Явно указываем parse_mode
                    logger.info(
                        f"Успешно отправлено уведомление о погоде пользователю {telegram_id_to_send} для города {city_name}."
                    )
                except Exception as e:
                    logger.error(
                        f"Ошибка при отправке уведомления о погоде пользователю {telegram_id_to_send} для города {city_name}: {e}",
                        exc_info=True,
                    )
            elif weather_data and weather_data.get("error"):
                # Логируем ошибку, полученную от API-клиента
                logger.warning(
                    f"Не удалось получить данные о погоде для рассылки (город: {city_name}): {weather_data.get('message')}"
                )
            else:
                # Логируем случай, когда API-клиент вернул None или неожиданный результат
                logger.warning(
                    f"Не удалось получить данные о погоде для рассылки (город: {city_name}), API вернул None или неожиданный результат."
                )
    logger.info("APScheduler: Задача send_weather_updates завершена.")


async def send_news_updates(bot: Bot) -> None:
    """
    Задача для рассылки обновлений новостей подписчикам.
    Получает активные подписки на новости, запрашивает данные и отправляет уведомления.

    Процесс работы:
    1. Получение списка активных подписок на новости
    2. Группировка подписчиков для минимизации дублирования
    3. Единый запрос новостей для всех подписчиков
    4. Форматирование общего сообщения
    5. Рассылка всем подписчикам

    Args:
        bot (Bot): Экземпляр бота Aiogram для отправки сообщений.

    Note:
        - Задача выполняется каждые 6 часов
        - Новости запрашиваются один раз для всех подписчиков
        - Сообщения форматируются с использованием HTML
        - Поддерживаются ссылки на источники
        - Отключается предпросмотр веб-страниц
        - Обрабатываются все возможные ошибки
    """
    logger.info("APScheduler: Запуск задачи send_news_updates...")
    all_news_subscriptions: List[Subscription] = []
    with get_session() as db_session:
        all_news_subscriptions = get_active_subscriptions_by_info_type(
            session=db_session, info_type=INFO_TYPE_NEWS
        )

    if not all_news_subscriptions:
        logger.info("Нет активных подписок на новости. Рассылка не требуется.")
        logger.info("APScheduler: Задача send_news_updates завершена.")
        return

    # Получаем уникальные user_id, подписанных на новости.
    # Это важно, чтобы каждый пользователь получил новости только один раз,
    # даже если у него несколько одинаковых подписок.
    user_ids_subscribed_to_news: List[int] = list(
        set([sub.user_id for sub in all_news_subscriptions if sub.user_id])
    )
    logger.info(
        f"Найдено {len(user_ids_subscribed_to_news)} уникальных пользователей, подписанных на новости."
    )

    if not user_ids_subscribed_to_news:
        logger.info(
            "APScheduler: Задача send_news_updates завершена (нет пользователей для рассылки)."
        )
        return

    # Получаем новости один раз для всех подписчиков
    articles_or_error: Optional[List[Dict[str, Any]]] | Dict[str, Any] = (
        await get_top_headlines(country="ru", page_size=5)
    )

    if isinstance(articles_or_error, dict) and articles_or_error.get("error"):
        logger.error(
            f"Ошибка API при получении новостей для рассылки: {articles_or_error.get('message')}"
        )
        logger.info("APScheduler: Задача send_news_updates завершена из-за ошибки API.")
        return

    if not isinstance(articles_or_error, list) or not articles_or_error:
        logger.info(
            "Не получено новостей от API или формат неверный. Рассылка новостей отменена."
        )
        logger.info("APScheduler: Задача send_news_updates завершена.")
        return

    # Формируем общее сообщение с новостями
    news_message_lines: List[str] = ["<b>📰 Свежие новости (Россия):</b>"]
    for i, article in enumerate(articles_or_error):
        title: str = html.escape(article.get("title", "Без заголовка"))
        url: str = article.get("url", "#")
        source: str = html.escape(
            article.get("source", {}).get("name", "Неизвестный источник")
        )
        news_message_lines.append(f"{i+1}. <a href='{url}'>{title}</a> ({source})")
    news_message_text: str = "\n".join(news_message_lines)

    # Рассылаем новости всем уникальным подписанным пользователям
    with get_session() as db_session:  # Отдельная сессия для получения User объектов
        for user_id in user_ids_subscribed_to_news:
            user: Optional[User] = db_session.get(User, user_id)
            if user and user.telegram_id:
                try:
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=news_message_text,
                        disable_web_page_preview=True,
                        parse_mode=ParseMode.HTML,
                    )  # Явно указываем parse_mode
                    logger.info(
                        f"Успешно отправлены новости пользователю {user.telegram_id}."
                    )
                except Exception as e:
                    logger.error(
                        f"Ошибка при отправке новостей пользователю {user.telegram_id}: {e}",
                        exc_info=True,
                    )
            else:
                logger.warning(
                    f"Не найден пользователь или telegram_id для user_id: {user_id} при рассылке новостей."
                )

    logger.info("APScheduler: Задача send_news_updates завершена.")


async def send_events_updates(bot: Bot) -> None:
    """
    Задача для рассылки обновлений о событиях KudaGo подписчикам.
    Получает активные подписки на события, запрашивает данные и отправляет уведомления.

    Процесс работы:
    1. Получение списка активных подписок на события
    2. Группировка подписчиков по городам для оптимизации запросов
    3. Для каждого города:
       - Запрос событий через API KudaGo
       - Форматирование сообщения с событиями
       - Рассылка всем подписчикам города

    Args:
        bot (Bot): Экземпляр бота Aiogram для отправки сообщений.

    Note:
        - Задача выполняется каждые 2 минуты (в тестовом режиме)
        - События группируются по городам для минимизации API-запросов
        - Сообщения форматируются с использованием HTML
        - Описания событий обрезаются для краткости
        - Поддерживаются ссылки на события
        - Обрабатываются все возможные ошибки
    """
    logger.info("APScheduler: Запуск задачи send_events_updates...")
    with get_session() as db_session:
        event_subscriptions: List[Subscription] = get_active_subscriptions_by_info_type(
            session=db_session, info_type=INFO_TYPE_EVENTS
        )
        logger.info(f"Найдено {len(event_subscriptions)} активных подписок на события.")

        # Группируем подписки по location_slug, чтобы делать один API запрос на город
        events_by_location_slug: Dict[str, List[Dict[str, Any]]] = (
            {}
        )  # Кэш для событий по городам
        users_for_location_slug: Dict[str, List[int]] = (
            {}
        )  # telegram_id пользователей по городам

        for sub in event_subscriptions:
            # Пропускаем подписки без необходимых деталей (location_slug) или user_id
            if not sub.details or not sub.user_id:
                logger.warning(
                    f"Пропуск подписки на события ID {sub.id}: отсутствует location_slug или user_id."
                )
                continue

            location_slug: str = sub.details
            user: Optional[User] = db_session.get(User, sub.user_id)
            if not user or not user.telegram_id:
                logger.warning(
                    f"Не найден пользователь или telegram_id для подписки на события ID {sub.id} (user_id: {sub.user_id})."
                )
                continue

            if location_slug not in users_for_location_slug:
                users_for_location_slug[location_slug] = []
            if (
                user.telegram_id not in users_for_location_slug[location_slug]
            ):  # Избегаем дублирования пользователя для одного города
                users_for_location_slug[location_slug].append(user.telegram_id)

        # Для каждого уникального location_slug получаем события
        for location_slug, user_telegram_ids in users_for_location_slug.items():
            if not user_telegram_ids:
                continue  # Пропускаем, если нет пользователей для этого города

            logger.info(f"Запрос событий KudaGo для location_slug: {location_slug}")
            # Получаем события через API клиент (запрашиваем, например, 3 ближайших события)
            kudago_result: Optional[List[Dict[str, Any]]] | Dict[str, Any] = (
                await get_kudago_events(location=location_slug, page_size=3)
            )

            if isinstance(kudago_result, dict) and kudago_result.get("error"):
                logger.error(
                    f"Ошибка API KudaGo при получении событий для '{location_slug}': {kudago_result.get('message')}"
                )
                continue  # Переходим к следующему городу, если есть ошибка API

            if not isinstance(kudago_result, list) or not kudago_result:
                logger.info(
                    f"Не найдено актуальных событий KudaGo для '{location_slug}'."
                )
                continue  # Пропускаем рассылку для этого города, если нет событий

            # Формируем сообщение о событиях
            # Пытаемся найти "человеческое" название города по его slug'у
            city_display_name: str = location_slug
            for name, slug_val in KUDAGO_LOCATION_SLUGS.items():
                if slug_val == location_slug:
                    city_display_name = name.capitalize()
                    break

            event_message_lines: List[str] = [
                f"<b>🎉 Ближайшие события в г. {html.escape(city_display_name)}:</b>"
            ]
            for i, event_data in enumerate(kudago_result):
                title: str = html.escape(event_data.get("title", "Без заголовка"))
                site_url: str = event_data.get("site_url", "#")
                # Очищаем и обрезаем описание для краткости в рассылке
                description_raw: str = event_data.get("description", "")
                description: str = html.unescape(
                    description_raw.replace("<p>", "")
                    .replace("</p>", "")
                    .replace("<br>", "\n")
                ).strip()

                event_str: str = f"{i+1}. <a href='{site_url}'>{title}</a>"
                if description:
                    max_desc_len = 70  # Короткое описание для рассылки
                    if len(description) > max_desc_len:
                        description = description[:max_desc_len] + "..."
                    event_str += f"\n   <i>{html.escape(description)}</i>"
                event_message_lines.append(event_str)

            event_message_text: str = "\n\n".join(event_message_lines)

            # Рассылаем сформированное сообщение всем подписчикам этого города
            for telegram_id in user_telegram_ids:
                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=event_message_text,
                        disable_web_page_preview=True,
                        parse_mode=ParseMode.HTML,
                    )
                    logger.info(
                        f"Успешно отправлены события пользователю {telegram_id} для города {city_display_name}."
                    )
                except Exception as e:
                    logger.error(
                        f"Ошибка при отправке событий пользователю {telegram_id} для города {city_display_name}: {e}",
                        exc_info=True,
                    )

    logger.info("APScheduler: Задача send_events_updates завершена.")
