import logging
from datetime import datetime
from aiogram import Bot
import html

from app.database.session import get_session
from app.database.crud import get_active_subscriptions_by_info_type, get_user_by_telegram_id
from app.api_clients.weather import get_weather_data
from app.api_clients.news import get_top_headlines
from app.api_clients.events import get_kudago_events
from app.bot.constants import INFO_TYPE_WEATHER, INFO_TYPE_NEWS, INFO_TYPE_EVENTS, KUDAGO_LOCATION_SLUGS
from app.database.models import User

logger = logging.getLogger(__name__)

async def test_scheduled_task():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"APScheduler: Тестовая задача выполнена в {current_time}!")


async def send_weather_updates(bot: Bot):
    # ... (код без изменений) ...
    logger.info("APScheduler: Запуск задачи send_weather_updates...")
    with next(get_session()) as db_session:
        weather_subscriptions = get_active_subscriptions_by_info_type(db_session, INFO_TYPE_WEATHER)
        logger.info(f"Найдено {len(weather_subscriptions)} активных подписок на погоду.")
        for sub in weather_subscriptions:
            if not sub.details or not sub.user_id: continue
            user = db_session.get(User, sub.user_id)
            if not user or not user.telegram_id: continue
            telegram_id_to_send = user.telegram_id;
            city_name = sub.details
            logger.info(f"Обработка подписки на погоду для {telegram_id_to_send}, город: {city_name}")
            weather_data = await get_weather_data(city_name)
            if weather_data and not weather_data.get("error"):
                try:
                    description = weather_data['weather'][0]['description'].capitalize();
                    temp = weather_data['main']['temp'];
                    feels_like = weather_data['main']['feels_like']
                    message_text = (f"🔔 <b>Ежедневный прогноз погоды для г. {html.escape(city_name)}:</b>\n"
                                    f"🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n☀️ Описание: {description}")
                    await bot.send_message(chat_id=telegram_id_to_send, text=message_text)
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления о погоде {telegram_id_to_send}: {e}")
            # ... (обработка ошибок API погоды) ...
    logger.info("APScheduler: Задача send_weather_updates завершена.")


async def send_news_updates(bot: Bot):
    """
    Задача для рассылки обновлений новостей (топ-5 для России).
    """
    logger.info("APScheduler: Запуск задачи send_news_updates...")
    # Получаем все подписки на новости, чтобы затем найти уникальных пользователей
    all_news_subscriptions = []
    with next(get_session()) as db_session:
        all_news_subscriptions = get_active_subscriptions_by_info_type(
            session=db_session,
            info_type=INFO_TYPE_NEWS
        )

    if not all_news_subscriptions:
        logger.info("Нет активных подписок на новости. Рассылка не требуется.")
        logger.info("APScheduler: Задача send_news_updates завершена.")
        return

    # Получаем уникальные user_id, подписанных на новости
    # (на случай, если у одного пользователя несколько одинаковых подписок, хотя этого быть не должно)
    user_ids_subscribed_to_news = list(set([sub.user_id for sub in all_news_subscriptions if sub.user_id]))
    logger.info(f"Найдено {len(user_ids_subscribed_to_news)} уникальных пользователей, подписанных на новости.")

    if not user_ids_subscribed_to_news:
        logger.info("APScheduler: Задача send_news_updates завершена (нет пользователей для рассылки).")
        return

    # Получаем новости один раз для всех
    articles_or_error = await get_top_headlines(country="ru", page_size=5)  # Запрашиваем 5 новостей

    if isinstance(articles_or_error, dict) and articles_or_error.get("error"):
        logger.error(f"Ошибка API при получении новостей для рассылки: {articles_or_error.get('message')}")
        logger.info("APScheduler: Задача send_news_updates завершена из-за ошибки API.")
        return

    if not isinstance(articles_or_error, list) or not articles_or_error:
        logger.info("Не получено новостей от API или формат неверный. Рассылка новостей отменена.")
        logger.info("APScheduler: Задача send_news_updates завершена.")
        return

    # Формируем общее сообщение с новостями
    news_message_lines = ["<b>📰 Свежие новости (Россия):</b>"]
    for i, article in enumerate(articles_or_error):
        title = html.escape(article.get('title', 'Без заголовка'))
        url = article.get('url', '#')
        source = html.escape(article.get('source', {}).get('name', 'Неизвестный источник'))
        news_message_lines.append(f"{i + 1}. <a href='{url}'>{title}</a> ({source})")
    news_message_text = "\n".join(news_message_lines)

    # Рассылаем новости всем подписанным пользователям
    with next(get_session()) as db_session:  # Новая сессия для получения telegram_id
        for user_id in user_ids_subscribed_to_news:
            user = db_session.get(User, user_id)
            if user and user.telegram_id:
                try:
                    await bot.send_message(chat_id=user.telegram_id, text=news_message_text,
                                           disable_web_page_preview=True)
                    logger.info(f"Успешно отправлены новости пользователю {user.telegram_id}.")
                except Exception as e:
                    logger.error(f"Ошибка при отправке новостей пользователю {user.telegram_id}: {e}")
            else:
                logger.warning(f"Не найден пользователь или telegram_id для user_id: {user_id} при рассылке новостей.")

    logger.info("APScheduler: Задача send_news_updates завершена.")


async def send_events_updates(bot: Bot):
    """
    Задача для рассылки обновлений о событиях KudaGo.
    """
    logger.info("APScheduler: Запуск задачи send_events_updates...")
    with next(get_session()) as db_session:
        event_subscriptions = get_active_subscriptions_by_info_type(
            session=db_session,
            info_type=INFO_TYPE_EVENTS
        )
        logger.info(f"Найдено {len(event_subscriptions)} активных подписок на события.")

        # Группируем подписки по location_slug, чтобы делать один API запрос на город
        events_by_location: dict[str, list[dict]] = {}
        users_for_location: dict[str, list[int]] = {}  # telegram_id пользователей

        for sub in event_subscriptions:
            if not sub.details or not sub.user_id:  # details это location_slug
                logger.warning(f"Пропуск подписки на события ID {sub.id}: отсутствует location_slug или user_id.")
                continue

            location_slug = sub.details
            user = db_session.get(User, sub.user_id)
            if not user or not user.telegram_id:
                logger.warning(
                    f"Не найден пользователь или telegram_id для подписки на события ID {sub.id} (user_id: {sub.user_id}).")
                continue

            if location_slug not in users_for_location:
                users_for_location[location_slug] = []
            if user.telegram_id not in users_for_location[
                location_slug]:  # Избегаем дублирования пользователя для одного города
                users_for_location[location_slug].append(user.telegram_id)

        # Получаем события для каждого уникального location_slug
        for location_slug, user_telegram_ids in users_for_location.items():
            if not user_telegram_ids: continue

            logger.info(f"Запрос событий KudaGo для location_slug: {location_slug}")
            # Запрашиваем, например, 3 ближайших события
            kudago_result = await get_kudago_events(location=location_slug, page_size=3)

            if isinstance(kudago_result, dict) and kudago_result.get("error"):
                logger.error(
                    f"Ошибка API KudaGo при получении событий для '{location_slug}': {kudago_result.get('message')}")
                continue  # Переходим к следующему городу

            if not isinstance(kudago_result, list) or not kudago_result:
                logger.info(f"Не найдено актуальных событий KudaGo для '{location_slug}'.")
                # Можно отправить сообщение "сегодня событий нет", но для начала пропустим
                continue

            # Формируем сообщение о событиях
            # Пытаемся найти "человеческое" название города
            city_display_name = location_slug
            for name, slug_val in KUDAGO_LOCATION_SLUGS.items():  # KUDAGO_LOCATION_SLUGS нужно импортировать
                if slug_val == location_slug:
                    city_display_name = name.capitalize()
                    break

            event_message_lines = [f"<b>🎉 Ближайшие события в г. {html.escape(city_display_name)}:</b>"]
            for i, event_data in enumerate(kudago_result):
                title = html.escape(event_data.get('title', 'Без заголовка'))
                site_url = event_data.get('site_url', '#')
                # Краткое описание, если есть
                description_raw = event_data.get('description', '')
                description = html.unescape(
                    description_raw.replace('<p>', '').replace('</p>', '').replace('<br>', '\n')).strip()

                event_str = f"{i + 1}. <a href='{site_url}'>{title}</a>"
                if description:
                    max_desc_len = 70  # Короткое описание для рассылки
                    if len(description) > max_desc_len:
                        description = description[:max_desc_len] + "..."
                    event_str += f"\n   <i>{html.escape(description)}</i>"
                event_message_lines.append(event_str)

            event_message_text = "\n\n".join(event_message_lines)

            # Рассылаем всем подписчикам этого города
            for telegram_id in user_telegram_ids:
                try:
                    await bot.send_message(chat_id=telegram_id, text=event_message_text, disable_web_page_preview=True)
                    logger.info(
                        f"Успешно отправлено уведомление о событиях для {location_slug} пользователю {telegram_id}.")
                except Exception as e:
                    logger.error(
                        f"Ошибка при отправке уведомления о событиях для {location_slug} пользователю {telegram_id}: {e}")

    logger.info("APScheduler: Задача send_events_updates завершена.")
