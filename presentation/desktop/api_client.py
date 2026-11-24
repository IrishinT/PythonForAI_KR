import json

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, QUrlQuery, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

DEFAULT_API_URL = "http://127.0.0.1:8000"
RECONNECT_INTERVAL_MS = 5000
HEALTH_INTERVAL_MS = 15000


class PredictionClient(QObject):
    server_status = Signal(str)
    predicted = Signal(bool, float, str, str)
    failed = Signal(str)

    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url.strip().rstrip("/")
        url = QUrl(self.base_url)
        if (
            not url.isValid()
            or url.scheme() not in ("http", "https")
            or not url.host()
            or url.hasQuery()
            or url.hasFragment()
        ):
            raise ValueError("Укажите адрес API, например http://127.0.0.1:8000")
        self.network = QNetworkAccessManager(self)
        self._health_reply = None
        self._prediction_reply = None
        self.health_timer = QTimer(self)
        self.health_timer.setSingleShot(True)
        self.health_timer.timeout.connect(self.check_health)

    def request(self, path, **parameters):
        url = QUrl(self.base_url + path)
        query = QUrlQuery()
        for name, value in parameters.items():
            if value is not None:
                query.addQueryItem(name, value)
        if not query.isEmpty():
            url.setQuery(query)
        request = QNetworkRequest(url)
        request.setRawHeader(b"Accept", b"application/json")
        request.setTransferTimeout(7000)
        return request

    def get_data(self, path, callback, **parameters):
        reply = self.network.get(self.request(path, **parameters))
        reply.finished.connect(lambda: callback(*self.read_reply(reply)))

    def get_image(self, path, callback, **parameters):
        request = self.request(path, **parameters)
        request.setRawHeader(b"Accept", b"image/png")
        reply = self.network.get(request)
        reply.finished.connect(lambda: callback(*self.read_reply_bytes(reply)))

    def check_health(self):
        if self._prediction_reply is not None:
            return False
        if self._health_reply is not None:
            return True
        self.health_timer.stop()
        reply = self.network.get(self.request("/health"))
        self._health_reply = reply
        reply.finished.connect(lambda: self.read_health(reply))
        return True

    def read_health(self, reply):
        if reply is not self._health_reply:
            reply.deleteLater()
            return
        self._health_reply = None
        status, payload = self.read_reply(reply)
        state = "offline" if status is None else "error"
        if status == 200 and payload.get("status") == "ok":
            state = "online"
        self.update_server_status(state)

    def update_server_status(self, state):
        interval = HEALTH_INTERVAL_MS if state == "online" else RECONNECT_INTERVAL_MS
        self.health_timer.start(interval)
        self.server_status.emit(state)

    def predict(self, weather, model_version=None, model_id=None):
        if self._prediction_reply is not None:
            return
        self.health_timer.stop()
        # Запрос прогноза сам проверит связь. Старый ответ /health здесь уже не нужен.
        health_reply, self._health_reply = self._health_reply, None
        if health_reply is not None:
            health_reply.abort()
        request = self.request("/predict", model_version=model_version, model_id=model_id)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        body = QByteArray(json.dumps(weather, allow_nan=False).encode("utf-8"))
        reply = self.network.post(request, body)
        self._prediction_reply = reply
        reply.finished.connect(lambda: self.read_prediction(reply))

    def read_prediction(self, reply):
        self._prediction_reply = None
        status, payload = self.read_reply(reply)
        if status is None:
            self.update_server_status("offline")
            self.failed.emit("Проверьте, запущен ли сервер прогноза, и попробуйте ещё раз.")
            return
        if status != 200:
            self.update_server_status("online" if status in (404, 422) else "error")
            message = {
                404: "Выбранная модель недоступна. Выберите другую модель и повторите запрос.",
                422: "Проверьте введённые данные и повторите запрос.",
            }.get(status, "Не удалось получить прогноз. Попробуйте ещё раз.")
            self.failed.emit(message)
            return

        rain = payload.get("rain_tomorrow")
        probability = payload.get("probability")
        version = payload.get("model_version")
        model_id = payload.get("model_id")
        if (
            type(rain) is not bool
            or type(probability) not in (float, int)
            or not 0 <= probability <= 1
        ):
            self.update_server_status("error")
            self.failed.emit("Не удалось прочитать прогноз. Попробуйте ещё раз.")
            return
        self.update_server_status("online")
        self.predicted.emit(
            rain, float(probability), version if isinstance(version, str) else "",
            model_id if isinstance(model_id, str) else "",
        )

    @staticmethod
    def read_reply_bytes(reply):
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        body = bytes(reply.readAll())
        error = reply.error()
        reply.deleteLater()
        if status == 200 and error != QNetworkReply.NetworkError.NoError:
            return None, b""
        return status, body

    @classmethod
    def read_reply(cls, reply):
        status, body = cls.read_reply_bytes(reply)
        try:
            payload = json.loads(body)
        except ValueError:
            payload = {}
        return status, payload if isinstance(payload, dict) else {}
