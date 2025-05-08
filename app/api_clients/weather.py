import httpx
from typing import Optional, Dict, Any
from app.config import settings # Импортируем наши настройки для доступа к API ключу
import logging

logger = logging.getLogger(__name__)

# Базовый URL для API OpenWeatherMap
BASE_OPENWEATHERMAP_URL = "https://api.openweathermap.org/data/2.5/weather"

async def get_weather_data(city_name: str) -> Optional[Dict[str, Any]]:
    """
    Получает данные о текущей погоде для указанного города из API OpenWeatherMap.

    Args:
        city_name (str): Название города, для которого запрашивается погода.

    Returns:
        Optional[Dict[str, Any]]: Словарь с данными о погоде, если запрос успешен,
                                  иначе None.
    """
    if not settings.WEATHER_API_KEY:
        logger.error("WEATHER_API_KEY не установлен в настройках.")
        return None

    # Параметры запроса
    params = {
        "q": city_name,          # Название города
        "appid": settings.WEATHER_API_KEY, # Наш API ключ
        "units": "metric",       # Единицы измерения (metric для Цельсия)
        "lang": "ru"             # Язык ответа (русский)
    }

    try:
        # Используем асинхронный HTTP клиент httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(BASE_OPENWEATHERMAP_URL, params=params)
            response.raise_for_status()  # Вызовет исключение для HTTP ошибок (4xx или 5xx)
            weather_data = response.json() # Парсим JSON ответ
            logger.info(f"Успешно получены данные о погоде для города '{city_name}': {weather_data}")
            return weather_data
    except httpx.HTTPStatusError as e:
        # Ошибка ответа от сервера (например, город не найден - 404, или проблема с ключом - 401)
        logger.error(f"Ошибка HTTP при запросе погоды для города '{city_name}': {e.response.status_code} - {e.response.text}")
        # Можно вернуть текст ошибки от API, если он информативен
        # Например, если response.json() содержит {"cod": "404", "message": "city not found"}
        try:
            error_details = e.response.json()
            return {"error": True, "status_code": e.response.status_code, "message": error_details.get("message", e.response.text)}
        except Exception: # Если ответ не JSON
            return {"error": True, "status_code": e.response.status_code, "message": e.response.text}
    except httpx.RequestError as e:
        # Ошибка сети или другая проблема с запросом
        logger.error(f"Ошибка сети при запросе погоды для города '{city_name}': {e}")
        return {"error": True, "message": "Сетевая ошибка при запросе к сервису погоды."}
    except Exception as e:
        # Другие непредвиденные ошибки
        logger.error(f"Непредвиденная ошибка при запросе погоды для города '{city_name}': {e}", exc_info=True)
        return {"error": True, "message": "Неизвестная ошибка при получении данных о погоде."}

# Пример использования (можно будет удалить или закомментировать)
async def main():
    city = "London"
    data = await get_weather_data(city)
    if data and not data.get("error"):
        print(f"Погода в городе {city}:")
        print(f"  Температура: {data['main']['temp']}°C")
        print(f"  Ощущается как: {data['main']['feels_like']}°C")
        print(f"  Описание: {data['weather'][0]['description']}")
        print(f"  Ветер: {data['wind']['speed']} м/с")
    elif data and data.get("error"):
        print(f"Ошибка получения погоды: {data.get('message')}")
    else:
        print(f"Не удалось получить данные о погоде для города {city}.")

#if __name__ == "__main__":
#    import asyncio
#    asyncio.run(main())