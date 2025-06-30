# Файл: app/scheduler/tasks.py

import logging
import html
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlmodel import Session, select

from app.api_clients.events import get_kudago_events
from app.api_clients.news import get_top_headlines
from app.api_clients.weather import get_weather_data
from app.bot.constants import INFO_TYPE_WEATHER, INFO_TYPE_NEWS, INFO_TYPE_EVENTS, KUDAGO_LOCATION_SLUGS
from app.database.crud import delete_subscription
from app.database.models import Subscription, User
from app.database.session import get_session

logger = logging.getLogger(__name__)


async def format_weather_message(details: str) -> Optional[str]:
    # ... (код без изменений) ...
    weather_data = await get_weather_data(details)
    if not weather_data or weather_data.get("error"):
        logger.warning(f"Не удалось получить данные о погоде для '{details}' в задаче планировщика.")
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


async def format_news_message() -> Optional[str]:
    # ... (код без изменений) ...
    articles = await get_top_headlines(page_size=5)
    if not isinstance(articles, list) or not articles:
        logger.warning("Не удалось получить новости в задаче планировщика.")
        return None

    response_lines = ["<b>📰 Последние главные новости (США):</b>"]
    for i, article in enumerate(articles):
        title = html.escape(article.get("title", "Без заголовка"))
        url = article.get("url", "#")
        response_lines.append(f"{i + 1}. <a href='{url}'>{title}</a>")
    return "\n".join(response_lines)


async def format_events_message(location_slug: str) -> Optional[str]:
    # ... (код без изменений) ...
    events = await get_kudago_events(location=location_slug, page_size=3)
    if not isinstance(events, list) or not events:
        logger.warning(f"Не удалось получить события для '{location_slug}' в задаче планировщика.")
        return None

    city_display_name = next((name.capitalize() for name, slug in KUDAGO_LOCATION_SLUGS.items() if slug == location_slug), location_slug)
    response_lines = [f"<b>🎉 Актуальные события в городе {html.escape(city_display_name)}:</b>"]
    for i, event in enumerate(events):
        title = html.escape(event.get("title", "Без заголовка"))
        site_url = event.get("site_url", "#")
        response_lines.append(f"{i + 1}. <a href='{site_url}'>{title}</a>")
    return "\n\n".join(response_lines)


async def send_single_notification(bot: Bot, subscription_id: int):
    """
    Отправляет одно уведомление по ID подписки.
    """
    logger.info(f"Запуск задачи для подписки ID: {subscription_id}")
    message_text: Optional[str] = None

    with get_session() as session:
        subscription = session.get(Subscription, subscription_id)

        if not subscription or subscription.status != "active":
            logger.warning(f"Подписка ID {subscription_id} не найдена или неактивна. Задача будет пропущена.")
            return

        # ИЗМЕНЕНО: Явно получаем пользователя, чтобы избежать путаницы
        user = subscription.user
        if not user:
            logger.error(f"Не найден связанный пользователь для подписки ID {subscription_id}.")
            return

        if subscription.info_type == INFO_TYPE_WEATHER:
            message_text = await format_weather_message(subscription.details)
        elif subscription.info_type == INFO_TYPE_NEWS:
            message_text = await format_news_message()
        elif subscription.info_type == INFO_TYPE_EVENTS:
            message_text = await format_events_message(subscription.details)

        if not message_text:
            logger.warning(f"Не удалось сформировать сообщение для подписки ID {subscription_id}. Пропуск отправки.")
            return

        try:
            # ИЗМЕНЕНО: используем user.telegram_id
            await bot.send_message(
                chat_id=user.telegram_id,
                text=message_text,
                disable_web_page_preview=True
            )
            logger.info(f"Успешно отправлено уведомление по подписке ID {subscription_id} пользователю {user.telegram_id}.")
        except TelegramAPIError as e:
            if "bot was blocked by the user" in e.message or "user is deactivated" in e.message:
                logger.warning(f"Пользователь {user.telegram_id} заблокировал бота. Деактивируем все его подписки.")
                # Получаем все подписки этого пользователя
                user_subscriptions = session.exec(select(Subscription).where(Subscription.user_id == user.id)).all()
                for sub in user_subscriptions:
                    # Используем существующую сессию для удаления
                    delete_subscription(session, sub.id)
                logger.info(f"Все подписки для пользователя {user.telegram_id} деактивированы.")
            else:
                logger.error(
                    f"Ошибка Telegram API при отправке уведомления по подписке ID {subscription_id}: {e}",
                    exc_info=True
                )
        except Exception as e:
            logger.error(
                f"Непредвиденная ошибка при отправке уведомления по подписке ID {subscription_id}: {e}",
                exc_info=True
            )