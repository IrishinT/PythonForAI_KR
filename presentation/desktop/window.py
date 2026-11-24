from PySide6.QtCore import QPointF, QRegularExpression, QSignalBlocker, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyleOptionSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from presentation.desktop.metrics import MetricsPanel
from presentation.weather_input import (
    DECIMAL_PATTERN,
    LOCATIONS,
    MEASUREMENTS,
    PRESSURE_HINT,
    WIND_DIRECTIONS,
    format_probability,
    measurement_range,
    parse_measurement,
)
from weather_contract import WEATHER_LIMITS

MEASUREMENT_STEPS = {"MinTemp": 0.5, "Rainfall": 0.1}


def label(text, name):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def update_state(widget, name, value):
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class WeatherIcon(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(96, 96)
        self.rain = None

    def set_rain(self, rain):
        self.rain = rain
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#8a9bad"), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        if self.rain is False:
            pen.setColor(QColor("#a76616"))
            painter.setPen(pen)
            painter.setBrush(QColor("#fff0d7"))
            painter.translate(48, 48)
            painter.drawEllipse(QPointF(0, 0), 15, 15)
            for _ in range(8):
                painter.drawLine(0, -23, 0, -30)
                painter.rotate(45)
            return

        ink = "#366491" if self.rain else "#8a9bad"
        fill = "#e7f0fa" if self.rain else "#edf1f5"
        pen.setColor(QColor(ink))
        painter.setPen(pen)
        painter.setBrush(QColor(fill))
        if self.rain is None:
            painter.translate(0, 8)
        cloud = QPainterPath(QPointF(26, 57))
        cloud.cubicTo(8, 57, 13, 32, 29, 35)
        cloud.cubicTo(32, 17, 57, 18, 61, 34)
        cloud.cubicTo(82, 29, 88, 57, 69, 57)
        cloud.closeSubpath()
        painter.drawPath(cloud)
        if self.rain:
            pen.setColor(QColor("#3878bb"))
            painter.setPen(pen)
            for x in (37, 50, 63):
                painter.drawLine(x, 66, x - 4, 75)


class ChoiceBox(QComboBox):
    def __init__(self, placeholder):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(14)
        self.currentTextChanged.connect(self.setToolTip)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#677789"), 1.5))
        x, y = self.width() - 16, self.height() / 2
        painter.drawLine(QPointF(x - 4, y - 2), QPointF(x, y + 2))
        painter.drawLine(QPointF(x, y + 2), QPointF(x + 4, y - 2))


class MeasurementSpinBox(QAbstractSpinBox):
    def __init__(self, name, example):
        super().__init__()
        self.minimum, self.maximum = WEATHER_LIMITS[name]
        self.start_value = float(example.replace(",", "."))
        self.step = MEASUREMENT_STEPS.get(name, 1)
        editor = self.lineEdit()
        editor.setPlaceholderText(f"{self.minimum}–{self.maximum}")
        editor.setMaxLength(24)
        editor.setTextMargins(10, 0, 0, 0)
        editor.setValidator(QRegularExpressionValidator(QRegularExpression(DECIMAL_PATTERN), editor))

    def number(self):
        try:
            return float(self.text().replace(",", "."))
        except ValueError:
            return None

    def stepEnabled(self):
        value = self.number()
        flags = self.StepEnabledFlag.StepNone
        if value is None or value < self.maximum:
            flags |= self.StepEnabledFlag.StepUpEnabled
        if value is None or value > self.minimum:
            flags |= self.StepEnabledFlag.StepDownEnabled
        return flags

    def stepBy(self, steps):
        value = self.number()
        value = self.start_value if value is None else value + steps * self.step
        value = min(max(value, self.minimum), self.maximum)
        text = f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        self.lineEdit().setText(text)

    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        enabled = self.stepEnabled() if self.isEnabled() else self.StepEnabledFlag.StepNone
        buttons = (
            (QStyle.SubControl.SC_SpinBoxUp, self.StepEnabledFlag.StepUpEnabled, -1),
            (QStyle.SubControl.SC_SpinBoxDown, self.StepEnabledFlag.StepDownEnabled, 1),
        )
        for control, flag, direction in buttons:
            bounds = self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, control, self)
            x, y = bounds.center().x(), bounds.center().y()
            ink = "#52677d" if enabled & flag else "#aebac5"
            painter.setPen(QPen(QColor(ink), 1.5))
            painter.drawLine(QPointF(x - 4, y - 2 * direction), QPointF(x, y + 2 * direction))
            painter.drawLine(QPointF(x, y + 2 * direction), QPointF(x + 4, y - 2 * direction))

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class ForecastWindow(QMainWindow):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self.entries = {}
        self.connection_error = False
        self.loading = False
        self.releases = {}
        self.latest_version = None
        self.catalog_pending = False
        self.legacy_api = False
        self.metrics_request = 0
        self.setWindowTitle("Дождь завтра")
        self.resize(1080, 770)
        self.setMinimumSize(840, 580)

        page = QWidget()
        page.setObjectName("page")
        self.setCentralWidget(page)

        body = QVBoxLayout(page)
        body.setContentsMargins(34, 24, 34, 20)
        body.setSpacing(15)

        top = QHBoxLayout()
        top.setSpacing(8)

        heading = QVBoxLayout()
        heading.setSpacing(6)
        heading.addWidget(label("Будет ли завтра дождь?", "heading"))
        heading.addWidget(label("Прогноз по данным сегодняшних наблюдений.", "subtitle"))
        top.addLayout(heading)
        top.addStretch()
        self.status_dot = QFrame()
        self.status_dot.setObjectName("statusDot")
        self.status_dot.setFixedSize(14, 14)
        top.addWidget(self.status_dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.status = label("", "serverStatus")
        self.status.setToolTip(client.base_url)
        top.addWidget(self.status, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.retry_button = QPushButton("Повторить")
        self.retry_button.setObjectName("retryConnection")
        self.retry_button.setAccessibleName("Повторить подключение")
        self.retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_button.clicked.connect(self.retry_connection)
        top.addWidget(self.retry_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        body.addLayout(top)
        body.addWidget(self.build_model_selector())

        forecast_page = QWidget()
        forecast_page.setObjectName("page")
        panels = QHBoxLayout(forecast_page)
        panels.setContentsMargins(20, 18, 20, 20)
        panels.setSpacing(28)
        panels.addWidget(self.build_form(), stretch=3)
        panels.addWidget(self.build_result(), stretch=2)
        forecast_scroll = QScrollArea()
        forecast_scroll.setWidgetResizable(True)
        forecast_scroll.setWidget(forecast_page)

        self.tabs = QTabWidget()
        self.metrics_panel = MetricsPanel()
        self.tabs.addTab(forecast_scroll, "Прогноз")
        self.tabs.addTab(self.metrics_panel, "Метрики")
        self.tabs.currentChanged.connect(self.refresh_metrics)
        body.addWidget(self.tabs, stretch=1)

        self.client.server_status.connect(self.show_server_status)
        self.client.predicted.connect(self.show_prediction)
        self.client.failed.connect(self.show_error)
        self.update_controls()
        self.retry_connection()

    def build_model_selector(self):
        container = QWidget()
        layout = QGridLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(5)
        self.version_box = ChoiceBox("Выберите версию")
        self.model_box = ChoiceBox("Выберите модель")
        self.version_box.currentIndexChanged.connect(self.show_release_models)
        self.model_box.currentIndexChanged.connect(self.model_changed)
        layout.addWidget(self.field("Версия модели", self.version_box), 0, 0)
        layout.addWidget(self.field("Модель", self.model_box), 0, 1)
        layout.setColumnStretch(1, 1)
        self.catalog_status = label("Загружаем список моделей…", "resultCaption")
        layout.addWidget(self.catalog_status, 1, 0, 1, 2)
        return container

    def refresh_catalog(self):
        if self.catalog_pending:
            return
        self.catalog_pending = True
        self.catalog_status.setText("Загружаем список моделей…")
        self.catalog_status.show()
        self.client.get_data("/models/versions", self.show_catalog)

    def show_catalog(self, status, payload):
        self.catalog_pending = False
        versions = payload.get("versions")
        if status != 200 or not isinstance(versions, list) or not versions:
            self.legacy_api = status == 404 and not self.releases
            message = "Доступна модель сервера по умолчанию." if self.legacy_api else "Не удалось загрузить список моделей."
            self.catalog_status.setText(message)
            self.catalog_status.show()
            self.update_controls()
            return

        version, model_id = self.selection()
        self.releases = {release["model_version"]: release for release in versions}
        self.latest_version = payload["latest_version"]
        self.legacy_api = False
        with QSignalBlocker(self.version_box):
            self.version_box.clear()
            for release_version in self.releases:
                text = f"{release_version} (последняя)" if release_version == self.latest_version else release_version
                self.version_box.addItem(text, release_version)
            selected_version = version if version in self.releases else self.latest_version
            self.version_box.setCurrentIndex(max(0, self.version_box.findData(selected_version)))
        self.catalog_status.hide()
        self.populate_models(model_id if selected_version == version else None)

    def show_release_models(self):
        self.populate_models()

    def populate_models(self, preferred=None):
        version = self.version_box.currentData()
        release = self.releases.get(version)
        with QSignalBlocker(self.model_box):
            self.model_box.clear()
            if release:
                default = release["default_model_id"]
                for model in release["models"]:
                    model_id, name = model["model_id"], model["model_name"]
                    recommended = version == self.latest_version and model_id == default
                    text = f"{name} (рекомендуемая)" if recommended else name
                    self.model_box.addItem(text, model_id)
                    if recommended:
                        self.model_box.setItemData(
                            self.model_box.count() - 1, QBrush(QColor("#286a48")), Qt.ItemDataRole.ForegroundRole,
                        )
                index = self.model_box.findData(preferred or default)
                if index < 0:
                    index = self.model_box.findData(default)
                self.model_box.setCurrentIndex(max(0, index))
        self.model_changed()

    def selection(self):
        return self.version_box.currentData(), self.model_box.currentData()

    def model_changed(self):
        version, model_id = self.selection()
        release = self.releases.get(version)
        recommended = bool(release and version == self.latest_version and model_id == release["default_model_id"])
        update_state(self.model_box, "recommended", recommended)
        if not self.loading:
            self.clear_feedback()
        self.update_controls()
        self.refresh_metrics()

    def refresh_metrics(self):
        self.metrics_request += 1
        if self.tabs.currentWidget() is not self.metrics_panel:
            return
        version, model_id = self.selection()
        if version is None or model_id is None:
            self.metrics_panel.show_status("Выберите модель, чтобы посмотреть её метрики.")
            return
        self.metrics_panel.show_status("Загружаем метрики модели…")
        request_id = self.metrics_request

        def display(status, payload):
            if request_id != self.metrics_request:
                return
            if status == 200 and (payload.get("model_version"), payload.get("model_id")) == (version, model_id):
                for chart_id in self.metrics_panel.show_metrics(payload):
                    self.client.get_image(
                        f"/models/metrics/{chart_id}",
                        lambda status, content, key=chart_id: display_image(key, status, content),
                        model_version=version, model_id=model_id,
                    )
            else:
                self.metrics_panel.show_status("Не удалось загрузить метрики модели. Переключите вкладку, чтобы повторить.")

        def display_image(chart_id, status, content):
            if request_id == self.metrics_request:
                self.metrics_panel.charts[chart_id].show_image(content if status == 200 else b"")

        self.client.get_data("/models/metrics", display, model_version=version, model_id=model_id)

    def build_form(self):
        form = QWidget()
        layout = QVBoxLayout(form)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(label("Наблюдения", "sectionTitle"))

        fields = QGridLayout()
        fields.setHorizontalSpacing(15)
        fields.setVerticalSpacing(14)
        fields.setColumnStretch(0, 1)
        fields.setColumnStretch(1, 1)

        self.location = ChoiceBox("Выберите город или станцию")
        for city in LOCATIONS:
            self.location.addItem(city, city)
        self.location.setCurrentIndex(-1)
        self.location.currentIndexChanged.connect(self.clear_feedback)
        fields.addWidget(self.field("Место наблюдения", self.location), 0, 0, 1, 2)

        for index, (name, title, unit, example) in enumerate(MEASUREMENTS):
            entry = MeasurementSpinBox(name, example)
            hint = f"Допустимо {measurement_range(name, unit)}."
            if name == "Pressure3pm":
                hint = f"{hint} {PRESSURE_HINT}"
            entry.setToolTip(hint)
            entry.lineEdit().textChanged.connect(self.clear_feedback)
            entry.lineEdit().returnPressed.connect(self.submit)
            self.entries[name] = entry
            row, column = divmod(index, 2)
            fields.addWidget(self.field(f"{title}, {unit}", entry), row + 1, column)

        self.wind = ChoiceBox("Выберите направление")
        for code, title in WIND_DIRECTIONS:
            self.wind.addItem(f"{code} · {title}", code)
        self.wind.setCurrentIndex(-1)
        self.wind.currentIndexChanged.connect(self.clear_feedback)
        fields.addWidget(self.field("Направление ветра в 15:00", self.wind), 3, 1)
        QWidget.setTabOrder(self.entries["WindGustSpeed"], self.wind)
        layout.addLayout(fields)

        self.message = label("", "message")
        self.message.setWordWrap(True)
        self.message.hide()
        layout.addWidget(self.message)

        self.submit_button = QPushButton("Получить прогноз")
        self.submit_button.setObjectName("submit")
        self.submit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_button.setMinimumWidth(170)
        self.submit_button.clicked.connect(self.submit)
        layout.addWidget(self.submit_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return form

    @staticmethod
    def field(title, control):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title_label = label(title, "fieldLabel")
        title_label.setWordWrap(True)
        title_label.setBuddy(control)
        control.setAccessibleName(title)
        control.setMinimumHeight(42)
        layout.addWidget(title_label)
        layout.addWidget(control)
        return wrapper

    def build_result(self):
        self.result_card = QFrame()
        self.result_card.setObjectName("resultCard")
        layout = QVBoxLayout(self.result_card)
        layout.setContentsMargins(24, 23, 24, 26)
        layout.setSpacing(8)
        layout.addWidget(label("Прогноз на завтра", "sectionTitle"))
        layout.addStretch()

        self.weather_icon = WeatherIcon()
        layout.addWidget(self.weather_icon, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.verdict = label("Прогноз ещё не получен", "verdict")
        self.verdict.setWordWrap(True)
        self.verdict.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.verdict)
        self.place = label("", "resultPlace")
        self.place.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.place)
        self.result_model = label("", "resultCaption")
        self.result_model.setWordWrap(True)
        self.result_model.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_model.hide()
        layout.addWidget(self.result_model)
        layout.addSpacing(15)
        self.probability = label("—", "probability")
        layout.addWidget(self.probability, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(label("Вероятность дождя", "resultCaption"), alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        return self.result_card

    def retry_connection(self):
        if self.client.check_health():
            self.show_server_status("checking")

    def show_server_status(self, state):
        texts = {
            "checking": "Подключаемся…",
            "online": "Подключено",
            "offline": "Нет подключения",
            "error": "Ошибка сервиса",
        }
        previous = self.status_dot.property("state")
        self.status.setText(texts[state])
        update_state(self.status_dot, "state", state)
        self.retry_button.setVisible(state in ("offline", "error"))
        if state == "online" and self.connection_error:
            self.connection_error = False
            self.message.hide()
        if state == "online" and (previous != "online" or not self.releases and not self.legacy_api):
            self.refresh_catalog()
        if state in ("offline", "error") and not self.releases:
            self.catalog_status.setText("Список моделей появится после подключения к серверу.")
            self.catalog_status.show()

    def clear_feedback(self):
        self.message.hide()
        if self.weather_icon.rain is not None:
            self.weather_icon.set_rain(None)
            self.probability.setText("—")
            self.verdict.setText("Прогноз ещё не получен")
            self.place.clear()
            self.result_model.hide()
            self.result_card.setToolTip("")

    def read_form(self):
        weather = {"Location": self.location.currentData(), "WindDir3pm": self.wind.currentData()}
        for name, title, unit, _ in MEASUREMENTS:
            entry = self.entries[name]
            try:
                weather[name] = parse_measurement(name, title, unit, entry.text())
            except ValueError as error:
                return None, entry, str(error)

        if not weather["Location"]:
            return None, self.location, "Выберите место наблюдения."
        if not weather["WindDir3pm"]:
            return None, self.wind, "Выберите направление ветра в 15:00."
        return weather, None, ""

    def submit(self):
        if not self.submit_button.isEnabled():
            return
        weather, invalid, message = self.read_form()
        if invalid is not None:
            self.connection_error = False
            self.message.setText(message)
            self.message.show()
            invalid.setFocus()
            return
        self.clear_feedback()
        self.set_loading(True)
        self.verdict.setText("Рассчитываем прогноз…")
        self.client.predict(weather, *self.selection())

    def set_loading(self, loading):
        self.loading = loading
        self.update_controls()
        self.submit_button.setText("Рассчитываем…" if loading else "Получить прогноз")

    def update_controls(self):
        for control in (*self.entries.values(), self.location, self.wind, self.retry_button):
            control.setEnabled(not self.loading)
        self.version_box.setEnabled(not self.loading and bool(self.releases))
        self.model_box.setEnabled(not self.loading and self.model_box.count() > 0)
        self.submit_button.setEnabled(not self.loading and (self.model_box.currentData() is not None or self.legacy_api))

    def show_prediction(self, rain, probability, version, model_id):
        self.set_loading(False)
        self.weather_icon.set_rain(rain)
        self.probability.setText(format_probability(probability))
        self.verdict.setText("Ожидается дождь" if rain else "Дождь не ожидается")
        self.place.setText(self.location.currentText())
        release = self.releases.get(version, {})
        name = next((entry["model_name"] for entry in release.get("models", []) if entry["model_id"] == model_id), model_id)
        details = " · ".join(value for value in (name, f"v{version}" if version else "") if value)
        self.result_model.setText(details)
        self.result_model.setVisible(bool(details))

    def show_error(self, message):
        self.set_loading(False)
        self.connection_error = self.status_dot.property("state") == "offline"
        self.verdict.setText("Прогноз ещё не получен")
        self.message.setText(message)
        self.message.show()
