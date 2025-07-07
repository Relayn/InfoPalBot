"""Модуль для взаимодействия с API сервиса погоды OpenWeatherMap.

Предоставляет асинхронную функцию для получения текущего прогноза погоды
для указанного города. Модуль инкапсулирует логику HTTP-запросов,
обработку ключей API и разбор ответов, включая обработку ошибок.
"""
import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_OPENWEATHERMAP_URL: str = "https://api.openweathermap.org/data/2.5/weather"


async def get_weather_data(city_name: str) -> Optional[Dict[str, Any]]:
    """Получает данные о погоде для города через OpenWeatherMap API.

    Выполняет асинхронный GET-запрос к API, запрашивая данные в метрической
    системе и на русском языке. Обрабатывает возможные ошибки, такие как
    неверный ключ API, сетевые проблемы или ошибки со стороны сервера API.

    Args:
        city_name: Название города, для которого запрашивается погода.

    Returns:
        Словарь с данными о погоде в случае успеха. Пример:
        {
            "main": {"temp": 20.5, "feels_like": 19.8, "humidity": 60},
            "weather": [{"description": "ясно"}],
            "wind": {"speed": 3.5},
            "name": "Москва"
        }

        Словарь с информацией об ошибке, если запрос не удался. Пример:
        {"error": True, "message": "city not found", "status_code": 404}

        None, если ключ WEATHER_API_KEY не установлен в настройках.
    """
    if not settings.WEATHER_API_KEY:
        logger.error(
            "WEATHER_API_KEY не установлен. Запрос погоды невозможен."
        )
        return None

    params: Dict[str, Any] = {
        "q": city_name,
        "appid": settings.WEATHER_API_KEY,
        "units": "metric",  # Градусы Цельсия
        "lang": "ru",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(BASE_OPENWEATHERMAP_URL, params=params)
            response.raise_for_status()
            weather_data = response.json()
            logger.info(f"Успешно получены данные о погоде для '{city_name}'.")
            return weather_data
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Ошибка HTTP при запросе погоды для '{city_name}': "
            f"{e.response.status_code} - {e.response.text}",
            exc_info=True,
        )
        try:
            error_details = e.response.json()
            message = error_details.get("message", e.response.text)
        except Exception:
            message = e.response.text
        return {
            "error": True,
            "status_code": e.response.status_code,
            "message": message,
        }
    except httpx.RequestError as e:
        logger.error(
            f"Сетевая ошибка при запросе погоды для '{city_name}': {e}",
            exc_info=True,
        )
        return {
            "error": True,
            "message": "Сетевая ошибка при запросе к сервису погоды.",
        }
    except Exception as e:
        logger.error(
            f"Непредвиденная ошибка при запросе погоды для '{city_name}': {e}",
            exc_info=True,
        )
        return {
            "error": True,
            "message": "Неизвестная ошибка при получении данных о погоде.",
        }