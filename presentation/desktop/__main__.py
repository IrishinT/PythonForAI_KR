from argparse import ArgumentParser

from PySide6.QtWidgets import QApplication

from .api_client import DEFAULT_API_URL, PredictionClient
from .style import STYLESHEET
from .window import ForecastWindow


def main():
    parser = ArgumentParser(description="Настольный клиент прогноза дождя")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Адрес сервера FastAPI")
    args = parser.parse_args()

    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    try:
        client = PredictionClient(args.api_url)
    except ValueError as error:
        parser.error(str(error))
    window = ForecastWindow(client)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
