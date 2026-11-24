from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

METRICS = {"ROC-AUC": "ROC-AUC", "Accuracy": "Accuracy", "F1-score": "F1", "Precision": "Precision", "Recall": "Recall"}
CHARTS = {
    "roc": "ROC",
    "precision-recall": "Precision–Recall",
    "learning-curve": "Кривая обучения",
    "confusion-matrix": "Матрица ошибок",
}


class ChartImage(QLabel):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("chartImage")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAccessibleName(title)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(254)
        self.image = QPixmap()

    def show_loading(self):
        self.image = QPixmap()
        self.setText(f"{self.accessibleName()} · загружаем…")

    def show_image(self, content):
        self.image = QPixmap()
        if self.image.loadFromData(content, "PNG"):
            self.fit_image()
        else:
            self.setText(f"Не удалось загрузить график «{self.accessibleName()}».")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_image()

    def fit_image(self):
        if not self.image.isNull():
            self.setPixmap(self.image.scaled(
                self.contentsRect().size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))


class MetricsPanel(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        page = QWidget()
        page.setObjectName("page")
        self.setWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        self.title = QLabel()
        self.title.setObjectName("sectionTitle")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.title)
        self.status = QLabel()
        self.status.setObjectName("resultCaption")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.cards = QWidget()
        summary = QHBoxLayout(self.cards)
        summary.setContentsMargins(0, 0, 0, 0)
        summary.setSpacing(10)
        self.values = {}
        for key, title in METRICS.items():
            card = QFrame()
            card.setObjectName("metricCard")
            column = QVBoxLayout(card)
            column.setContentsMargins(14, 9, 14, 9)
            column.addWidget(QLabel(title))
            value = QLabel()
            value.setObjectName("metricValue")
            value.setAccessibleName(title)
            column.addWidget(value)
            self.values[key] = value
            summary.addWidget(card, 1)
        layout.addWidget(self.cards)

        self.chart_grid = QWidget()
        grid = QGridLayout(self.chart_grid)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.charts = {key: ChartImage(title) for key, title in CHARTS.items()}
        for index, chart in enumerate(self.charts.values()):
            grid.addWidget(chart, *divmod(index, 2))
        layout.addWidget(self.chart_grid)
        layout.addStretch()
        self.show_status("Выберите модель, чтобы посмотреть её метрики.")

    def show_status(self, message):
        self.title.hide()
        self.cards.hide()
        self.chart_grid.hide()
        self.status.setText(message)
        self.status.show()

    def show_metrics(self, payload):
        self.title.setText(f"{payload['model_name']} · версия {payload['model_version']}")
        self.title.show()
        metrics = payload.get("metrics", {})
        for key, value_label in self.values.items():
            value = metrics.get(key)
            value_label.setText(f"{value:.4f}".replace(".", ",") if type(value) in (int, float) else "—")
        self.cards.show()

        available = [key for key in self.charts if key in payload.get("charts", [])]
        for key, chart in self.charts.items():
            if key in available:
                chart.show_loading()
            chart.setVisible(key in available)
        self.chart_grid.setVisible(bool(available))
        self.status.setText("Для этой модели сохранены только числовые метрики.")
        self.status.setVisible(not available)
        return available
