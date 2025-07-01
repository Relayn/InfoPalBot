import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlmodel import Session, select

from app.bot.handlers.subscription import (
    process_subscribe_command_start,
    process_info_type_choice,
    process_category_choice,
    process_frequency_choice,
)
from app.bot.fsm import SubscriptionStates
from app.database.models import Subscription
from app.database.crud import create_user
from app.bot.constants import INFO_TYPE_EVENTS
from tests.utils.mock_helpers import get_mock_fsm_context, get_mock_session_context_manager
from aiogram.types import Message, User as AiogramUser, CallbackQuery


@pytest.mark.asyncio
async def test_full_subscribe_to_events_with_category_flow(integration_session: Session):
    """
    Интеграционный тест: полная цепочка подписки на события с выбором категории.
    /subscribe -> Events -> Category 'concert' -> City 'msk' -> Frequency '24h'
    """
    telegram_user_id = 888001
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)
    fsm_context = await get_mock_fsm_context()

    mock_session_cm = get_mock_session_context_manager(integration_session)

    with patch("app.bot.handlers.subscription.get_session", return_value=mock_session_cm), \
         patch("app.bot.handlers.subscription.scheduler") as mock_scheduler:

        # --- Step 1: /subscribe ---
        mock_msg_start = AsyncMock(spec=Message, from_user=MagicMock(id=telegram_user_id))
        mock_msg_start.answer = AsyncMock()
        await process_subscribe_command_start(mock_msg_start, fsm_context)
        assert await fsm_context.get_state() == SubscriptionStates.choosing_info_type

        # --- Step 2: Choose info type 'events' ---
        cb_type = AsyncMock(spec=CallbackQuery, from_user=MagicMock(id=telegram_user_id),
                            data=f"subscribe_type:{INFO_TYPE_EVENTS}")
        cb_type.message = AsyncMock(spec=Message)
        cb_type.message.edit_text = AsyncMock()
        cb_type.answer = AsyncMock()
        await process_info_type_choice(cb_type, fsm_context)
        assert await fsm_context.get_state() == SubscriptionStates.choosing_category

        # --- Step 3: Choose category 'concert' ---
        cb_category = AsyncMock(spec=CallbackQuery, from_user=MagicMock(id=telegram_user_id),
                                data="subscribe_category:concert")
        cb_category.message = AsyncMock(spec=Message)
        cb_category.message.edit_text = AsyncMock()
        cb_category.answer = AsyncMock()
        await process_category_choice(cb_category, fsm_context)
        assert await fsm_context.get_state() == SubscriptionStates.prompting_city_search

        # --- Step 4: Search for city 'Мос' ---
        from app.bot.handlers.subscription import process_city_search, process_city_selection

        msg_search = AsyncMock(spec=Message, text="Мос", from_user=MagicMock(id=telegram_user_id))
        msg_search.answer = AsyncMock()
        await process_city_search(msg_search, fsm_context)
        assert await fsm_context.get_state() == SubscriptionStates.choosing_city_from_list

        # --- Step 5: Select city 'Москва' ---
        cb_city = AsyncMock(spec=CallbackQuery, from_user=MagicMock(id=telegram_user_id),
                            data="city_select:Москва")
        cb_city.message = AsyncMock(spec=Message)
        cb_city.message.edit_text = AsyncMock()
        cb_city.answer = AsyncMock()
        await process_city_selection(cb_city, fsm_context)
        assert await fsm_context.get_state() == SubscriptionStates.choosing_frequency

        # --- Step 6: Choose frequency '24h' ---
        cb_freq = AsyncMock(spec=CallbackQuery, from_user=MagicMock(id=telegram_user_id), data="frequency:24")
        cb_freq.message = AsyncMock(spec=Message)
        cb_freq.message.edit_text = AsyncMock()
        cb_freq.answer = AsyncMock()
        await process_frequency_choice(cb_freq, fsm_context)
        assert await fsm_context.get_state() is None

    # --- Проверки в БД и вызова планировщика ---
    final_sub = integration_session.exec(select(Subscription).where(Subscription.user_id == db_user.id)).one()
    assert final_sub.info_type == INFO_TYPE_EVENTS
    assert final_sub.details == "msk"  # slug для Москвы
    assert final_sub.category == "concert"
    assert final_sub.frequency == 24

    mock_scheduler.add_job.assert_called_once()
    _, kwargs = mock_scheduler.add_job.call_args
    assert kwargs["id"] == f"sub_{final_sub.id}"
    assert kwargs["trigger"] == "interval"
    assert kwargs["hours"] == 24