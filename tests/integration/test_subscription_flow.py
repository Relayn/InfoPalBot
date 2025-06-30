# Файл: tests/integration/test_subscription_flow.py

import pytest
import html
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from typing import Optional

from sqlmodel import Session, select

from app.bot.handlers.subscription import (
    process_subscribe_command_start,
    process_info_type_choice,
    process_frequency_choice,
)
from app.bot.fsm import SubscriptionStates
from app.database.models import User as DBUser, Subscription
from app.database.crud import create_user
from app.bot.constants import INFO_TYPE_NEWS
from aiogram.types import Message, User as AiogramUser, Chat, CallbackQuery
from tests.utils.mock_helpers import get_mock_fsm_context, get_mock_session_context_manager


@pytest.mark.asyncio
async def test_subscribe_to_news_interval_flow_and_job_added(integration_session: Session):
    """
    Интеграционный тест: успешная интервальная подписка на новости и добавление задачи.
    """
    telegram_user_id = 777001
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)
    fsm_context = await get_mock_fsm_context()
    mock_msg_start = AsyncMock(spec=Message, from_user=MagicMock(id=telegram_user_id))
    mock_msg_start.answer = AsyncMock()

    with patch("app.bot.handlers.subscription.get_session",
               return_value=get_mock_session_context_manager(integration_session)), \
            patch("app.bot.handlers.subscription.scheduler") as mock_scheduler:
        # Step 1: /subscribe
        await process_subscribe_command_start(mock_msg_start, fsm_context)

        # Step 2: Choose news
        cb_type = AsyncMock(spec=CallbackQuery, from_user=MagicMock(id=telegram_user_id),
                            data=f"subscribe_type:{INFO_TYPE_NEWS}")
        cb_type.message = AsyncMock(spec=Message);
        cb_type.message.edit_text = AsyncMock();
        cb_type.answer = AsyncMock()
        await process_info_type_choice(cb_type, fsm_context)

        # Step 3: Choose frequency (interval)
        cb_freq = AsyncMock(spec=CallbackQuery, from_user=MagicMock(id=telegram_user_id), data="frequency:24")
        cb_freq.message = AsyncMock(spec=Message);
        cb_freq.message.edit_text = AsyncMock();
        cb_freq.answer = AsyncMock()
        await process_frequency_choice(cb_freq, fsm_context)

    # --- Проверки ---
    final_sub = integration_session.exec(select(Subscription).where(Subscription.user_id == db_user.id)).one()
    assert final_sub.info_type == INFO_TYPE_NEWS
    assert final_sub.frequency == 24
    assert final_sub.cron_expression is None
    assert await fsm_context.get_state() is None

    mock_scheduler.add_job.assert_called_once()
    _, kwargs = mock_scheduler.add_job.call_args
    assert kwargs["id"] == f"sub_{final_sub.id}"
    assert kwargs["trigger"] == "interval"
    assert kwargs["hours"] == 24


@pytest.mark.asyncio
async def test_subscribe_to_news_cron_flow_and_job_added(integration_session: Session):
    """
    Интеграционный тест: успешная cron подписка на новости и добавление задачи.
    """
    telegram_user_id = 777002
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)
    fsm_context = await get_mock_fsm_context()
    mock_msg_start = AsyncMock(spec=Message, from_user=MagicMock(id=telegram_user_id))
    mock_msg_start.answer = AsyncMock()

    with patch("app.bot.handlers.subscription.get_session",
               return_value=get_mock_session_context_manager(integration_session)), \
            patch("app.bot.handlers.subscription.scheduler") as mock_scheduler:
        # Step 1: /subscribe
        await process_subscribe_command_start(mock_msg_start, fsm_context)

        # Step 2: Choose news
        cb_type = AsyncMock(spec=CallbackQuery, from_user=MagicMock(id=telegram_user_id),
                            data=f"subscribe_type:{INFO_TYPE_NEWS}")
        cb_type.message = AsyncMock(spec=Message);
        cb_type.message.edit_text = AsyncMock();
        cb_type.answer = AsyncMock()
        await process_info_type_choice(cb_type, fsm_context)

        # Step 3: Choose frequency (cron)
        cb_freq = AsyncMock(spec=CallbackQuery, from_user=MagicMock(id=telegram_user_id), data="cron:09:00")
        cb_freq.message = AsyncMock(spec=Message);
        cb_freq.message.edit_text = AsyncMock();
        cb_freq.answer = AsyncMock()
        await process_frequency_choice(cb_freq, fsm_context)

    # --- Проверки ---
    final_sub = integration_session.exec(select(Subscription).where(Subscription.user_id == db_user.id)).one()
    assert final_sub.info_type == INFO_TYPE_NEWS
    assert final_sub.cron_expression == "0 9 * * *"
    assert final_sub.frequency is None
    assert await fsm_context.get_state() is None

    mock_scheduler.add_job.assert_called_once()
    _, kwargs = mock_scheduler.add_job.call_args
    assert kwargs["id"] == f"sub_{final_sub.id}"
    assert kwargs["trigger"] == "cron"
    assert kwargs["hour"] == 9
    assert kwargs["minute"] == 0