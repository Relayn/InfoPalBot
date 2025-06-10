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
from datetime import datetime, timezone, timedelta
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
    Получает все активные подписки на погоду, проверяет для каждой, пора ли отправлять уведомление,
    и отправляет, если время пришло.
    """
    logger.info("APScheduler: Запуск задачи send_weather_updates...")
    with get_session() as db_session:
        weather_subscriptions: List[Subscription] = (
            get_active_subscriptions_by_info_type(
                session=db_session, info_type=INFO_TYPE_WEATHER
            )
        )
        logger.info(
            f"Найдено {len(weather_subscriptions)} активных подписок на погоду."
        )

        for sub in weather_subscriptions:
            now = datetime.now(timezone.utc)
            # Проверяем, пора ли отправлять уведомление
            if sub.last_sent_at and (now - sub.last_sent_at) < timedelta(
                hours=sub.frequency
            ):
                continue  # Еще не время

            if not sub.details or not sub.user or not sub.user.telegram_id:
                logger.warning(f"Пропуск подписки ID {sub.id}: неполные данные.")
                continue

            telegram_id_to_send = sub.user.telegram_id
            city_name = sub.details
            logger.info(
                f"Обработка подписки на погоду для пользователя {telegram_id_to_send}, город: {city_name}"
            )

            weather_data = await get_weather_data(city_name)
            if weather_data and not weather_data.get("error"):
                try:
                    description = weather_data["weather"][0]["description"].capitalize()
                    temp = weather_data["main"]["temp"]
                    feels_like = weather_data["main"]["feels_like"]
                    message_text = (
                        f"🔔 <b>Прогноз погоды для г. {html.escape(city_name)}:</b>\n"
                        f"🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n"
                        f"☀️ Описание: {description}"
                    )
                    await bot.send_message(
                        chat_id=telegram_id_to_send, text=message_text
                    )
                    logger.info(
                        f"Успешно отправлено уведомление о погоде пользователю {telegram_id_to_send}."
                    )

                    # Обновляем время последней отправки
                    sub.last_sent_at = now
                    db_session.add(sub)
                    db_session.commit()

                except Exception as e:
                    logger.error(
                        f"Ошибка при отправке уведомления о погоде пользователю {telegram_id_to_send}: {e}",
                        exc_info=True,
                    )
            elif weather_data and weather_data.get("error"):
                logger.warning(
                    f"Не удалось получить данные о погоде для рассылки (город: {city_name}): {weather_data.get('message')}"
                )
            else:
                logger.warning(
                    f"Не удалось получить данные о погоде для рассылки (город: {city_name}), API вернул None."
                )
    logger.info("APScheduler: Задача send_weather_updates завершена.")


async def send_news_updates(bot: Bot) -> None:
    """
    Задача для рассылки обновлений новостей подписчикам.
    Работает аналогично send_weather_updates, проверяя время для каждой подписки.
    """
    logger.info("APScheduler: Запуск задачи send_news_updates...")
    with get_session() as db_session:
        all_news_subscriptions = get_active_subscriptions_by_info_type(
            session=db_session, info_type=INFO_TYPE_NEWS
        )

        if not all_news_subscriptions:
            logger.info("Нет активных подписок на новости. Рассылка не требуется.")
            return

        users_to_notify: Dict[int, Subscription] = {}
        now = datetime.now(timezone.utc)

        for sub in all_news_subscriptions:
            if sub.user_id and (
                not sub.last_sent_at
                or (now - sub.last_sent_at) >= timedelta(hours=sub.frequency)
            ):
                # Если у пользователя несколько подписок на новости, выбираем самую "старую" для отправки
                if (
                    sub.user_id not in users_to_notify
                    or users_to_notify[sub.user_id].last_sent_at > sub.last_sent_at
                ):
                    users_to_notify[sub.user_id] = sub

        if not users_to_notify:
            logger.info("Для всех новостных подписок время отправки еще не наступило.")
            return

        logger.info(
            f"Найдено {len(users_to_notify)} пользователей для рассылки новостей."
        )

        articles = await get_top_headlines()
        # Проверяем, не вернул ли API ошибку в виде словаря
        if isinstance(articles, dict) and articles.get("error"):
            logger.error(
                f"Ошибка API при получении новостей: {articles.get('message')}"
            )
            return  # Прерываем выполнение, если API вернул ошибку

        if not articles:
            logger.warning("Нет новостей для рассылки.")
            return

        message_text = "🔔 <b>Свежие новости:</b>\n\n" + "\n\n".join(
            [f"▪️ <a href='{a['url']}'>{html.escape(a['title'])}</a>" for a in articles]
        )

        for user_id, sub_to_update in users_to_notify.items():
            try:
                telegram_id = sub_to_update.user.telegram_id
                await bot.send_message(
                    chat_id=telegram_id,
                    text=message_text,
                    disable_web_page_preview=True,
                )
                logger.info(f"Успешно отправлены новости пользователю {telegram_id}.")
                sub_to_update.last_sent_at = now
                db_session.add(sub_to_update)

            except Exception as e:
                logger.error(
                    f"Ошибка при отправке новостей пользователю (ID: {user_id}): {e}",
                    exc_info=True,
                )

        db_session.commit()

    logger.info("APScheduler: Задача send_news_updates завершена.")


async def send_events_updates(bot: Bot) -> None:
    """
    Задача для рассылки обновлений о событиях подписчикам.
    Работает аналогично send_weather_updates, проверяя время для каждой подписки.
    """
    logger.info("APScheduler: Запуск задачи send_events_updates...")
    with get_session() as db_session:
        events_subscriptions: List[Subscription] = (
            get_active_subscriptions_by_info_type(
                session=db_session, info_type=INFO_TYPE_EVENTS
            )
        )
        logger.info(
            f"Найдено {len(events_subscriptions)} активных подписок на события."
        )

        # Группируем подписчиков по городу (location_slug), чтобы делать один API запрос на город
        subscriptions_by_city: Dict[str, List[Subscription]] = {}
        for sub in events_subscriptions:
            if sub.details:
                if sub.details not in subscriptions_by_city:
                    subscriptions_by_city[sub.details] = []
                subscriptions_by_city[sub.details].append(sub)

        now = datetime.now(timezone.utc)

        for city_slug, subscriptions in subscriptions_by_city.items():
            # Проверяем, есть ли хотя бы один подписчик в этой группе, которому пора отправлять
            is_time_to_send_for_group = any(
                not sub.last_sent_at
                or (now - sub.last_sent_at) >= timedelta(hours=sub.frequency)
                for sub in subscriptions
            )

            if not is_time_to_send_for_group:
                continue

            logger.info(f"Запрос событий для города: {city_slug}")
            events_data = await get_kudago_events(location_slug=city_slug, page_size=5)

            if (
                not events_data
                or "results" not in events_data
                or not events_data["results"]
            ):
                logger.warning(f"Не найдено событий для города {city_slug}.")
                continue

            message_text = (
                f"🔔 <b>Ближайшие события для города с кодом '{html.escape(city_slug)}':</b>\n\n"
                + "\n\n".join(
                    [
                        f"▪️ <a href='{e['site_url']}'>{html.escape(e['title'])}</a>"
                        for e in events_data["results"]
                    ]
                )
            )

            for sub in subscriptions:
                # Повторно проверяем для каждого, т.к. в группе могут быть разные частоты
                if not sub.last_sent_at or (now - sub.last_sent_at) >= timedelta(
                    hours=sub.frequency
                ):
                    try:
                        telegram_id = sub.user.telegram_id
                        await bot.send_message(
                            chat_id=telegram_id,
                            text=message_text,
                            disable_web_page_preview=True,
                        )
                        logger.info(
                            f"Успешно отправлены события пользователю {telegram_id} для города {city_slug}."
                        )
                        sub.last_sent_at = now
                        db_session.add(sub)
                    except Exception as e:
                        logger.error(
                            f"Ошибка при отправке событий пользователю (ID: {sub.user_id}): {e}",
                            exc_info=True,
                        )

        db_session.commit()

    logger.info("APScheduler: Задача send_events_updates завершена.")
