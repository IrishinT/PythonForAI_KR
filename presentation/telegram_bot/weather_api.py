import asyncio
from urllib.parse import urlsplit

from aiohttp import ClientConnectionError, ClientError


class WeatherApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


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

    async def request(self, method, path, *, expected=200, **kwargs):
        async with self.session.request(method, self.base_url + path, allow_redirects=False, **kwargs) as response:
            if response.status != expected:
                raise WeatherApiError("Сервис не смог выполнить запрос. Попробуйте ещё раз.", response.status)
            payload = await response.json()
        if not isinstance(payload, dict):
            raise WeatherApiError("Не удалось прочитать ответ сервиса.")
        return payload

    async def is_connected(self):
        try:
            payload = await self.request("GET", "/health")
        except (ClientError, TimeoutError, ValueError, WeatherApiError):
            return False
        return payload.get("status") == "ok"

    async def predict(self, weather, *, model_version=None, model_id=None):
        params = self.model_params(model_version, model_id)
        for attempt in range(2):
            try:
                payload = await self.request("POST", "/predict", json=weather, params=params)
                break
            except WeatherApiError as error:
                if error.status == 404:
                    raise WeatherApiError("Выбранная модель недоступна. Выберите другую через /model.", 404) from error
                if error.status == 422:
                    raise WeatherApiError("Сервис не принял данные. Проверьте их и начните новый прогноз.", 422) from error
                raise
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
        return rain, probability, payload.get("model_version"), payload.get("model_id")

    @staticmethod
    def model_params(model_version, model_id=None):
        return {key: value for key, value in {"model_version": model_version, "model_id": model_id}.items() if value}

    async def get_data(self, path, **kwargs):
        try:
            return await self.request("GET", path, **kwargs)
        except (ClientError, TimeoutError, ValueError) as error:
            raise WeatherApiError("Не удалось получить ответ от сервиса прогноза.") from error

    async def versions(self):
        return await self.get_data("/models/versions")

    async def models(self, version):
        return await self.get_data("/models", params=self.model_params(version))

    async def metrics(self, *, model_version=None, model_id=None):
        return await self.get_data("/models/metrics", params=self.model_params(model_version, model_id))

    async def chart(self, chart_id, *, model_version, model_id):
        path = f"/models/metrics/{chart_id}"
        try:
            async with self.session.get(
                self.base_url + path, params=self.model_params(model_version, model_id), allow_redirects=False,
            ) as response:
                if response.status != 200 or response.content_type != "image/png":
                    raise WeatherApiError("График недоступен.", response.status)
                return await response.read()
        except (ClientError, TimeoutError, ValueError) as error:
            raise WeatherApiError("Не удалось загрузить график.") from error

    async def training(self, key, *, start=False):
        try:
            return await self.request(
                "POST" if start else "GET", "/models/training", expected=202 if start else 200,
                headers={"X-Master-Key": key},
            )
        except WeatherApiError as error:
            if error.status == 401:
                raise WeatherApiError("Сервер отклонил мастер-ключ бота.", 401) from error
            if error.status == 503:
                raise WeatherApiError("На сервере не настроено обучение.", 503) from error
            raise
        except (ClientError, TimeoutError, ValueError) as error:
            raise WeatherApiError("Не удалось связаться с сервером обучения.") from error
