"""Модуль, содержащий задачи для выполнения планировщиком.

Этот файл определяет конкретные функции, которые вызываются APScheduler
для выполнения фоновых задач, таких как отправка уведомлений по подпискам.
Он включает в себя как функции для форматирования сообщений на основе
данных из внешних API, так и основную функцию для отправки этих сообщений.

Задачи:
- `format_weather_message`: Формирует текст сообщения о погоде.
- `format_news_message`: Формирует текст сообщения о новостях.
- `format_events_message`: Формирует текст сообщения о событиях.
- `send_single_notification`: Основная задача, которая получает подписку,
  форматирует и отправляет соответствующее уведомление.
"""
import html
import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlmodel import select

from app.api_clients.events import get_kudago_events
from app.api_clients.news import get_top_headlines
from app.api_clients.weather import get_weather_data
from app.bot.constants import (
    EVENTS_CATEGORIES,
    INFO_TYPE_EVENTS,
    INFO_TYPE_NEWS,
    INFO_TYPE_WEATHER,
    KUDAGO_LOCATION_SLUGS,
    NEWS_CATEGORIES,
)
from app.database.crud import delete_subscription
from app.database.models import Subscription
from app.database.session import get_session

logger = logging.getLogger(__name__)


async def format_weather_message(details: str) -> Optional[str]:
    """Формирует текстовое сообщение с прогнозом погоды.

    Args:
        details: Название города для запроса погоды.

    Returns:
        Отформатированная строка с информацией о погоде или None при ошибке.
    """
    weather_data = await get_weather_data(details)
    if not weather_data or weather_data.get("error"):
        logger.warning(
            f"Не удалось получить данные о погоде для '{details}' в задаче."
        )
        return None

    try:
        description = weather_data["weather"][0]["description"].capitalize()
        temp = weather_data["main"]["temp"]
        feels_like = weather_data["main"]["feels_like"]
        city_name = weather_data.get("name", details)
        return (
            f"<b>Погода в городе {html.escape(city_name)}:</b>\n"
            f"🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n"
            f"☀️ Описание: {description}"
        )
    except (KeyError, IndexError) as e:
        logger.error(f"Ошибка парсинга данных о погоде для '{details}': {e}", exc_info=True)
        return None


async def format_news_message(category: Optional[str] = None) -> Optional[str]:
    """Формирует текстовое сообщение с последними новостями.

    Args:
        category: Slug категории новостей для запроса (например, 'sports').

    Returns:
        Отформатированная строка со списком новостей или None при ошибке.
    """
    articles = await get_top_headlines(category=category, page_size=5)
    if not isinstance(articles, list) or not articles:
        logger.warning(
            f"Не удалось получить новости для категории '{category}' в задаче."
        )
        return None

    category_display_name = NEWS_CATEGORIES.get(category)
    category_header = f" ({category_display_name})" if category_display_name else ""
    response_lines = [f"<b>📰 Последние главные новости (США){category_header}:</b>"]

    for i, article in enumerate(articles):
        title = html.escape(article.get("title", "Без заголовка"))
        url = article.get("url", "#")
        response_lines.append(f"{i + 1}. <a href='{url}'>{title}</a>")
    return "\n".join(response_lines)


async def format_events_message(
    location_slug: str, category: Optional[str] = None
) -> Optional[str]:
    """Формирует текстовое сообщение с актуальными событиями.

    Args:
        location_slug: Slug города для KudaGo API (например, 'msk').
        category: Slug категории событий для запроса (например, 'concert').

    Returns:
        Отформатированная строка со списком событий или None при ошибке.
    """
    events = await get_kudago_events(
        location=location_slug, categories=category, page_size=3
    )
    if not isinstance(events, list) or not events:
        logger.warning(
            f"Не удалось получить события для '{location_slug}' "
            f"(категория: {category}) в задаче."
        )
        return None

    city_display_name = next(
        (
            name.capitalize()
            for name, slug in KUDAGO_LOCATION_SLUGS.items()
            if slug == location_slug
        ),
        location_slug,
    )
    category_display_name = EVENTS_CATEGORIES.get(category)
    category_header = f" ({category_display_name})" if category_display_name else ""
    response_lines = [
        f"<b>🎉 Актуальные события в городе {html.escape(city_display_name)}"
        f"{category_header}:</b>"
    ]

    for i, event in enumerate(events):
        title = html.escape(event.get("title", "Без заголовка"))
        site_url = event.get("site_url", "#")
        response_lines.append(f"{i + 1}. <a href='{site_url}'>{title}</a>")
    return "\n\n".join(response_lines)


async def _get_formatted_message_for_subscription(
    subscription: Subscription,
) -> Optional[str]:
    """Выбирает и вызывает нужную функцию форматирования для подписки.

    Args:
        subscription: Объект подписки, для которой нужно создать сообщение.

    Returns:
        Готовая строка сообщения или None, если форматирование не удалось.
    """
    if subscription.info_type == INFO_TYPE_WEATHER:
        return await format_weather_message(subscription.details)
    if subscription.info_type == INFO_TYPE_NEWS:
        return await format_news_message(category=subscription.category)
    if subscription.info_type == INFO_TYPE_EVENTS:
        return await format_events_message(
            location_slug=subscription.details, category=subscription.category
        )
    return None


def _handle_user_blocking_error(session, user):
    """Обрабатывает ошибку блокировки бота пользователем.

    Деактивирует все подписки указанного пользователя.

    Args:
        session: Активная сессия SQLAlchemy.
        user: Объект пользователя, который заблокировал бота.
    """
    logger.warning(
        f"Пользователь {user.telegram_id} заблокировал бота. "
        "Деактивируем все его подписки."
    )
    user_subscriptions = session.exec(
        select(Subscription).where(Subscription.user_id == user.id)
    ).all()
    for sub in user_subscriptions:
        delete_subscription(session, sub.id)
    logger.info(f"Все подписки для пользователя {user.telegram_id} деактивированы.")


async def send_single_notification(bot: Bot, subscription_id: int):
    """Отправляет одно уведомление по ID подписки.

    Основная функция, вызываемая планировщиком. Она координирует получение
    данных, форматирование и отправку сообщения, а также обработку ошибок.

    Args:
        bot: Экземпляр `aiogram.Bot` для отправки сообщений.
        subscription_id: ID подписки из базы данных, для которой
            нужно отправить уведомление.
    """
    logger.info(f"Запуск задачи для подписки ID: {subscription_id}")

    with get_session() as session:
        subscription = session.get(Subscription, subscription_id)

        if not subscription or subscription.status != "active":
            logger.warning(
                f"Подписка ID {subscription_id} не найдена или неактивна. "
                "Задача будет пропущена."
            )
            return

        user = subscription.user
        if not user:
            logger.error(
                f"Не найден связанный пользователь для подписки ID {subscription_id}."
            )
            return

        message_text = await _get_formatted_message_for_subscription(subscription)
        if not message_text:
            logger.warning(
                f"Не удалось сформировать сообщение для подписки ID {subscription_id}. "
                "Пропуск отправки."
            )
            return

        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=message_text,
                disable_web_page_preview=True,
            )
            logger.info(
                f"Успешно отправлено уведомление по подписке ID {subscription_id} "
                f"пользователю {user.telegram_id}."
            )
        except TelegramAPIError as e:
            if "bot was blocked by the user" in e.message or "user is deactivated" in e.message:
                _handle_user_blocking_error(session, user)
            else:
                logger.error(
                    f"Ошибка Telegram API при отправке уведомления по подписке "
                    f"ID {subscription_id}: {e}",
                    exc_info=True,
                )
        except Exception as e:
            logger.error(
                f"Непредвиденная ошибка при отправке уведомления по подписке "
                f"ID {subscription_id}: {e}",
                exc_info=True,
            )