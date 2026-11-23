from argparse import ArgumentParser
from os import getenv
from pathlib import Path

from PySide6.QtWidgets import QApplication
from dotenv import load_dotenv

from .api_client import DEFAULT_API_URL, PredictionClient
from .style import STYLESHEET
from .window import ForecastWindow


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    api_url = getenv("WEATHER_API_URL", "").strip() or DEFAULT_API_URL
    parser = ArgumentParser(description="Настольный клиент прогноза дождя")
    parser.add_argument("--api-url", default=api_url, help="Адрес сервера FastAPI")
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
