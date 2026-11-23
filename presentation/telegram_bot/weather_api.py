import asyncio
from urllib.parse import urlsplit

from aiohttp import ClientConnectionError, ClientError


class WeatherApiError(Exception):
    pass


class WeatherApi:
    def __init__(self, session, base_url):
        self.session = session
        self.base_url = base_url.strip().rstrip("/")
        try:
            url = urlsplit(self.base_url)
        except ValueError:
            raise ValueError("Проверьте WEATHER_API_URL в файле .env.") from None
        if url.scheme not in ("http", "https") or not url.hostname or url.query or url.fragment:
            raise ValueError("Проверьте WEATHER_API_URL в файле .env.")

    async def request(self, method, path, **kwargs):
        async with self.session.request(method, self.base_url + path, **kwargs) as response:
            if response.status == 422:
                raise WeatherApiError("Сервис не принял данные. Проверьте их и начните новый прогноз.")
            if response.status != 200:
                raise WeatherApiError("Не удалось получить прогноз. Попробуйте ещё раз.")
            payload = await response.json()
        if not isinstance(payload, dict):
            raise WeatherApiError("Не удалось прочитать прогноз. Попробуйте ещё раз.")
        return payload

    async def is_connected(self):
        try:
            payload = await self.request("GET", "/health")
        except (ClientError, TimeoutError, ValueError, WeatherApiError):
            return False
        return payload.get("status") == "ok"

    async def predict(self, weather):
        for attempt in range(2):
            try:
                payload = await self.request("POST", "/predict", json=weather)
                break
            except (ClientConnectionError, TimeoutError):
                if attempt == 1:
                    raise WeatherApiError("Нет подключения к сервису прогноза.") from None
                await asyncio.sleep(1)
            except (ClientError, ValueError):
                raise WeatherApiError("Не удалось прочитать прогноз. Попробуйте ещё раз.") from None

        rain = payload.get("rain_tomorrow")
        probability = payload.get("probability")
        if (
            type(rain) is not bool
            or type(probability) not in (int, float)
            or not 0 <= probability <= 1
        ):
            raise WeatherApiError("Не удалось прочитать прогноз. Попробуйте ещё раз.")
        return rain, probability
