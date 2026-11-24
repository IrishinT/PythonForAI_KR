from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class TrainingPanel(QWidget):
    release_published = Signal(str)

    def __init__(self, client, master_key=""):
        super().__init__()
        self.client = client
        self.request_id = 0
        self.pending = False
        self.running = False
        self.reported_version = None
        self.poll = QTimer(self)
        self.poll.setSingleShot(True)
        self.poll.timeout.connect(self.check_status)

        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(12)
        heading = QLabel("Обучение моделей")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        summary = QLabel("Сервер обучит все модели на подготовленной выборке и опубликует новый выпуск.")
        summary.setObjectName("resultCaption")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        caption = QLabel("Мастер-ключ")
        caption.setObjectName("fieldLabel")
        self.key = QLineEdit(master_key)
        self.key.setObjectName("trainingKey")
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("Вставьте мастер-ключ")
        self.key.setAccessibleName(caption.text())
        self.key.setMinimumHeight(42)
        self.key.setMaximumWidth(430)
        caption.setBuddy(self.key)
        layout.addWidget(caption)
        layout.addWidget(self.key)

        self.start_button = QPushButton("Запустить обучение")
        self.start_button.setObjectName("submit")
        self.start_button.setMinimumWidth(185)
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.start_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.status = QLabel()
        self.status.setObjectName("resultCaption")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch()
        self.key.textChanged.connect(self.key_changed)
        self.start_button.clicked.connect(self.start_training)
        self.key_changed()

    def showEvent(self, event):
        super().showEvent(event)
        self.check_status()

    def key_changed(self):
        self.request_id += 1
        self.pending = self.running = False
        self.poll.stop()
        self.update_button()
        if self.key.text():
            self.status.setText("Проверяем статус обучения…")
            if self.isVisible():
                self.poll.start(350)
        else:
            self.status.setText("Введите мастер-ключ, чтобы запустить обучение.")

    def update_button(self):
        self.start_button.setEnabled(bool(self.key.text()) and not self.pending and not self.running)

    def check_status(self):
        self.send_request(start=False)

    def start_training(self):
        self.send_request(start=True)

    def send_request(self, *, start):
        if not self.key.text() or self.pending or (start and self.running):
            return
        self.poll.stop()
        self.pending = True
        self.update_button()
        self.request_id += 1
        request_id = self.request_id
        if start:
            self.status.setText("Запускаем обучение…")

        def display(status, payload):
            if request_id == self.request_id:
                self.show_status(status, payload, start=start)

        self.client.training(self.key.text(), display, start=start)

    def show_status(self, status, payload, *, start):
        self.pending = False
        state = payload.get("status") if status in (200, 202) else None
        previously_running = self.running
        retry = False
        self.running = state == "running" or status == 409
        if self.running:
            self.status.setText("Обучение идёт на сервере. Прогнозы доступны во время обучения.")
        elif state == "idle":
            self.status.setText("Можно запустить обучение нового выпуска.")
        elif state == "succeeded" and isinstance(payload.get("model_version"), str):
            version = payload["model_version"]
            self.status.setText(f"Обучение завершено. Выпуск {version} опубликован.")
            if version != self.reported_version:
                self.reported_version = version
                self.release_published.emit(version)
        elif state == "failed":
            self.status.setText("Обучение завершилось ошибкой. Подробности в журнале сервера.")
        elif status == 401:
            self.status.setText("Сервер отклонил мастер-ключ.")
        elif status == 503:
            self.status.setText("На сервере не задан мастер-ключ для обучения.")
        elif status == 404:
            self.status.setText("Эта версия сервера не поддерживает запуск обучения.")
        else:
            retry = previously_running or start
            self.running = retry
            self.status.setText("Не удалось получить статус обучения. Повторяем запрос…" if retry else "Не удалось получить статус обучения.")
        self.update_button()
        if self.running or retry:
            self.poll.start(2000)
