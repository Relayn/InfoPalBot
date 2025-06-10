"""
Вспомогательные утилиты для создания моков в тестах.
"""

from typing import Optional
from unittest.mock import MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.fsm.storage.memory import MemoryStorage
from sqlmodel import Session


async def get_mock_fsm_context(
    initial_state: Optional[State] = None, initial_data: Optional[dict] = None
) -> FSMContext:
    """Создает и возвращает настроенный мок FSMContext."""
    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=MagicMock())
    if initial_state:
        await state.set_state(initial_state)
    if initial_data:
        await state.set_data(initial_data)
    return state


def get_mock_session_context_manager(session: Session) -> MagicMock:
    """Создает и возвращает мок контекстного менеджера для сессии."""
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = session
    mock_cm.__exit__.return_value = None
    return mock_cm
