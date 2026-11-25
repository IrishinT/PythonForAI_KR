from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget


STAGE_NAMES = {
    "preparing": "Подготовка данных",
    "searching": "Подбор гиперпараметров",
    "fitting": "Обучение модели",
    "evaluating": "Оценка на тестовой выборке",
    "charting": "Подготовка графиков",
    "publishing": "Публикация выпуска",
}


def stage_description(payload):
    stage_id = payload.get("stage")
    stage = STAGE_NAMES.get(stage_id)
    model = payload.get("model_name")
    if stage_id == "fitting" and model:
        return f"Обучение {model}"
    return f"{stage} для модели {model}" if model and stage else stage


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

        self.progress = QProgressBar()
        self.progress.setObjectName("trainingProgress")
        self.progress.setAccessibleName("Готовые модели")
        self.progress.setMaximumWidth(430)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.detail = QLabel()
        self.detail.setObjectName("resultCaption")
        self.detail.setTextFormat(Qt.TextFormat.PlainText)
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
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
        self.show_progress({})
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
            self.show_progress({})
            self.status.setText("Запускаем обучение…")

        def display(status, payload):
            if request_id == self.request_id:
                self.show_status(status, payload, start=start)

        self.client.training(self.key.text(), display, start=start)

    def show_progress(self, payload):
        completed, total = payload.get("completed_models"), payload.get("total_models")
        detail = []
        if type(completed) is int and type(total) is int and 0 <= completed <= total and total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(completed)
            self.progress.show()
            detail.append(f"Готово {completed} из {total} моделей")
        else:
            self.progress.hide()
        elapsed = payload.get("elapsed_seconds")
        if type(elapsed) is int and elapsed >= 0:
            minutes, seconds = divmod(elapsed, 60)
            duration = f"{minutes} мин {seconds:02d} с" if minutes else f"{seconds} с"
            detail.append(f"Прошло {duration}")
        self.detail.setText(". ".join(detail))
        self.detail.setVisible(bool(detail))

    def show_status(self, status, payload, *, start):
        self.pending = False
        state = payload.get("status") if status in (200, 202) else None
        previously_running = self.running
        retry = False
        self.running = state == "running" or status == 409
        stage = stage_description(payload)
        if self.running:
            self.status.setText(stage or "Обучение идёт на сервере.")
        elif state == "idle":
            self.status.setText("Можно запустить обучение нового выпуска.")
        elif state == "succeeded" and isinstance(payload.get("model_version"), str):
            version = payload["model_version"]
            message = f"Выпуск {version} опубликован."
            best_model, score = payload.get("best_model_name"), payload.get("best_roc_auc")
            if isinstance(best_model, str) and type(score) in (int, float):
                roc_auc = f"{score:.4f}".replace(".", ",")
                message += f" Модель {best_model} показала лучший ROC-AUC ({roc_auc})."
            self.status.setText(message)
            if version != self.reported_version:
                self.reported_version = version
                self.release_published.emit(version)
        elif state == "failed":
            message = f"Сбой на этапе «{stage}»." if stage else "Обучение завершилось ошибкой."
            self.status.setText(f"{message} Можно повторить запуск. Подробности в журнале сервера.")
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
        if state in ("running", "failed", "succeeded"):
            self.show_progress(payload)
        elif not self.running:
            self.show_progress({})
        self.update_button()
        if self.running or retry:
            self.poll.start(2000)
