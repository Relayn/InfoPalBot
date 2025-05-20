import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from typing import List, Dict, Any, Optional

from aiogram import Bot  # Для мокирования экземпляра бота
from app.scheduler.tasks import send_weather_updates, send_news_updates, send_events_updates
from app.database.models import User as DBUser, Subscription as DBSubscription
from app.bot.constants import INFO_TYPE_WEATHER, INFO_TYPE_NEWS, INFO_TYPE_EVENTS
# KUDAGO_LOCATION_SLUGS может понадобиться для проверки деталей в логах или ответах, если мы его используем в задачах
from app.bot.constants import KUDAGO_LOCATION_SLUGS


# Фикстура для мокированного экземпляра бота
@pytest.fixture
def mock_bot() -> AsyncMock:
    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock()
    return bot


# Фикстура для мокированной сессии БД
@pytest.fixture
def mock_db_session() -> MagicMock:
    session = MagicMock()
    session.get = MagicMock()  # Мокируем метод get
    return session


# Фикстура для мокирования get_session()
@pytest.fixture
def mock_get_session_context(mock_db_session: MagicMock) -> MagicMock:
    mock_session_cm = MagicMock()
    mock_session_cm.__enter__.return_value = mock_db_session

    mock_generator = MagicMock()
    mock_generator.__next__.return_value = mock_session_cm

    # Патчим get_session в модуле tasks, где он используется
    with patch('app.scheduler.tasks.get_session', return_value=mock_generator) as patched_get_session:
        yield patched_get_session


# --- Тесты для send_weather_updates ---
@pytest.mark.asyncio
async def test_send_weather_updates_sends_to_subscribed_user(mock_bot: AsyncMock, mock_db_session: MagicMock,
                                                             mock_get_session_context: MagicMock):
    user_id = 1
    telegram_id = 12345
    city = "Москва"
    mock_user = DBUser(id=user_id, telegram_id=telegram_id)
    # В задачах планировщика мы не можем полагаться на загрузку user через sub.user,
    # так как сессия может быть другой. Поэтому get(User, sub.user_id) - правильный подход.
    mock_subscription = DBSubscription(id=1, user_id=user_id, info_type=INFO_TYPE_WEATHER, details=city,
                                       status="active")

    mock_db_session.get.return_value = mock_user

    mock_weather_data = {
        "weather": [{"description": "ясно"}],
        "main": {"temp": 20.0, "feels_like": 19.5},
        "name": city
    }

    with patch('app.scheduler.tasks.get_active_subscriptions_by_info_type',
               return_value=[mock_subscription]) as mock_get_subs, \
            patch('app.scheduler.tasks.get_weather_data', return_value=mock_weather_data) as mock_get_weather_api:
        await send_weather_updates(mock_bot)

        mock_get_subs.assert_called_once_with(mock_db_session, INFO_TYPE_WEATHER)  # <--- ИЗМЕНЕНИЕ
        mock_db_session.get.assert_called_once_with(DBUser, user_id)
        mock_get_weather_api.assert_called_once_with(city)
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert call_args.kwargs['chat_id'] == telegram_id
        assert city in call_args.kwargs['text']
        assert "20.0°C" in call_args.kwargs['text']


@pytest.mark.asyncio
async def test_send_weather_updates_no_active_subscriptions(mock_bot: AsyncMock, mock_db_session: MagicMock,
                                                            mock_get_session_context: MagicMock):
    with patch('app.scheduler.tasks.get_active_subscriptions_by_info_type', return_value=[]) as mock_get_subs, \
            patch('app.scheduler.tasks.get_weather_data') as mock_get_weather_api:
        await send_weather_updates(mock_bot)

        mock_get_subs.assert_called_once_with(mock_db_session, INFO_TYPE_WEATHER)  # <--- ИЗМЕНЕНИЕ
        mock_get_weather_api.assert_not_called()
        mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_weather_updates_api_error(mock_bot: AsyncMock, mock_db_session: MagicMock,
                                              mock_get_session_context: MagicMock):
    user_id = 1;
    telegram_id = 12345;
    city = "ОшибкаГород"
    mock_user = DBUser(id=user_id, telegram_id=telegram_id)
    mock_subscription = DBSubscription(id=1, user_id=user_id, info_type=INFO_TYPE_WEATHER, details=city,
                                       status="active", user=mock_user)
    mock_db_session.get.return_value = mock_user
    mock_api_error = {"error": True, "message": "API Error"}

    with patch('app.scheduler.tasks.get_active_subscriptions_by_info_type', return_value=[mock_subscription]), \
            patch('app.scheduler.tasks.get_weather_data', return_value=mock_api_error) as mock_get_weather_api:
        await send_weather_updates(mock_bot)

        mock_get_weather_api.assert_called_once_with(city)
        mock_bot.send_message.assert_not_called()  # Сообщение не должно быть отправлено при ошибке API


# --- Тесты для send_news_updates ---
@pytest.mark.asyncio
async def test_send_news_updates_sends_to_subscribed_users(mock_bot: AsyncMock, mock_db_session: MagicMock,
                                                           mock_get_session_context: MagicMock):
    user1 = DBUser(id=1, telegram_id=111)
    user2 = DBUser(id=2, telegram_id=222)
    # Две подписки от разных пользователей на новости
    mock_subscriptions = [
        DBSubscription(id=1, user_id=user1.id, info_type=INFO_TYPE_NEWS, status="active", user=user1),
        DBSubscription(id=2, user_id=user2.id, info_type=INFO_TYPE_NEWS, status="active", user=user2)
    ]

    # Мокируем session.get для обоих пользователей
    def mock_session_get_side_effect(model_cls, user_id_val):
        if model_cls == DBUser and user_id_val == user1.id: return user1
        if model_cls == DBUser and user_id_val == user2.id: return user2
        return None

    mock_db_session.get.side_effect = mock_session_get_side_effect

    mock_articles = [
        {'title': 'Новость дня', 'url': 'http://news.com/1', 'source': {'name': 'Новостной Портал'}},
    ]
    with patch('app.scheduler.tasks.get_active_subscriptions_by_info_type',
               return_value=mock_subscriptions) as mock_get_subs, \
            patch('app.scheduler.tasks.get_top_headlines', return_value=mock_articles) as mock_get_headlines_api:

        await send_news_updates(mock_bot)

        mock_get_subs.assert_called_once_with(session=mock_db_session, info_type=INFO_TYPE_NEWS)
        mock_get_headlines_api.assert_called_once_with(country="ru", page_size=5)
        assert mock_bot.send_message.call_count == 2  # Одно сообщение каждому пользователю
        # Проверяем, что сообщение было отправлено обоим
        mock_bot.send_message.assert_any_call(chat_id=user1.telegram_id, text=ANY, disable_web_page_preview=True)
        mock_bot.send_message.assert_any_call(chat_id=user2.telegram_id, text=ANY, disable_web_page_preview=True)


@pytest.mark.asyncio
async def test_send_news_updates_api_returns_error(mock_bot: AsyncMock, mock_db_session: MagicMock,
                                                   mock_get_session_context: MagicMock):
    user1 = DBUser(id=1, telegram_id=111)
    mock_subscriptions = [DBSubscription(id=1, user_id=user1.id, info_type=INFO_TYPE_NEWS, status="active", user=user1)]
    mock_api_error = {"error": True, "message": "News API Error"}

    with patch('app.scheduler.tasks.get_active_subscriptions_by_info_type', return_value=mock_subscriptions), \
            patch('app.scheduler.tasks.get_top_headlines', return_value=mock_api_error) as mock_get_headlines_api:
        await send_news_updates(mock_bot)
        mock_get_headlines_api.assert_called_once()
        mock_bot.send_message.assert_not_called()


# --- Тесты для send_events_updates ---
@pytest.mark.asyncio
async def test_send_events_updates_sends_to_subscribed_users(mock_bot: AsyncMock, mock_db_session: MagicMock,
                                                             mock_get_session_context: MagicMock):
    user1_msk = DBUser(id=1, telegram_id=111)
    user2_msk = DBUser(id=2, telegram_id=222)  # Другой пользователь, тот же город
    user3_spb = DBUser(id=3, telegram_id=333)  # Пользователь для другого города

    mock_subscriptions = [
        DBSubscription(id=1, user_id=user1_msk.id, info_type=INFO_TYPE_EVENTS, details="msk", status="active",
                       user=user1_msk),
        DBSubscription(id=2, user_id=user2_msk.id, info_type=INFO_TYPE_EVENTS, details="msk", status="active",
                       user=user2_msk),
        DBSubscription(id=3, user_id=user3_spb.id, info_type=INFO_TYPE_EVENTS, details="spb", status="active",
                       user=user3_spb),
    ]

    # Мокируем session.get для всех пользователей
    def mock_session_get_side_effect_events(model_cls, user_id_val):
        if model_cls == DBUser:
            if user_id_val == user1_msk.id: return user1_msk
            if user_id_val == user2_msk.id: return user2_msk
            if user_id_val == user3_spb.id: return user3_spb
        return None

    mock_db_session.get.side_effect = mock_session_get_side_effect_events

    mock_events_msk = [{'title': 'Событие в Москве', 'site_url': 'http://msk.event', 'description': 'Описание мск'}]
    mock_events_spb = [{'title': 'Событие в СПб', 'site_url': 'http://spb.event', 'description': 'Описание спб'}]

    # Мокируем get_kudago_events, чтобы он возвращал разные данные для разных городов
    async def mock_get_kudago_side_effect(location: str, page_size: int):
        if location == "msk": return mock_events_msk
        if location == "spb": return mock_events_spb
        return []

    with patch('app.scheduler.tasks.get_active_subscriptions_by_info_type',
               return_value=mock_subscriptions) as mock_get_subs, \
            patch('app.scheduler.tasks.get_kudago_events',
                  side_effect=mock_get_kudago_side_effect) as mock_get_kudago_api:

        await send_events_updates(mock_bot)

        mock_get_subs.assert_called_once_with(session=mock_db_session, info_type=INFO_TYPE_EVENTS)
        assert mock_get_kudago_api.call_count == 2  # Один вызов для msk, один для spb
        mock_get_kudago_api.assert_any_call(location="msk", page_size=3)
        mock_get_kudago_api.assert_any_call(location="spb", page_size=3)

        assert mock_bot.send_message.call_count == 3  # 2 сообщения для msk, 1 для spb
        # Проверяем, что сообщения содержат правильные данные
        calls = mock_bot.send_message.call_args_list

        texts_sent = [c.kwargs['text'] for c in calls]
        chat_ids_sent = [c.kwargs['chat_id'] for c in calls]

        assert user1_msk.telegram_id in chat_ids_sent
        assert user2_msk.telegram_id in chat_ids_sent
        assert user3_spb.telegram_id in chat_ids_sent

        assert any("Событие в Москве" in text for text in texts_sent)
        assert any("Событие в СПб" in text for text in texts_sent)