STYLESHEET = """
QMainWindow, #page, QScrollArea {
    background: #ffffff;
}
QScrollArea {
    border: 0;
}
QScrollBar:vertical {
    width: 10px;
    background: #ffffff;
}
QScrollBar:horizontal {
    height: 10px;
    background: #ffffff;
}
QScrollBar::handle {
    background: #bac6d2;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
QWidget {
    color: #202c39;
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
}
QLabel {
    background: transparent;
}
#serverStatus {
    color: #536477;
    font-size: 13px;
    font-weight: 500;
}
#statusDot {
    border: 3px solid #edf0f3;
    border-radius: 7px;
    background: #8795a5;
}
#statusDot[state="online"] {
    border-color: #e3f2ea;
    background: #318359;
}
#statusDot[state="offline"], #statusDot[state="error"] {
    border-color: #f8eddc;
    background: #a66620;
}
#retryConnection {
    min-height: 28px;
    padding: 0 7px;
    border: 1px solid transparent;
    border-radius: 5px;
    background: transparent;
    color: #255b9f;
    font-size: 13px;
    font-weight: 600;
}
#retryConnection:hover, #retryConnection:focus {
    background: #eaf1fa;
}
#retryConnection:focus {
    border-color: #3265a6;
}
#retryConnection:disabled {
    color: #687888;
}
#heading {
    font-size: 36px;
    font-weight: 700;
}
#subtitle {
    font-size: 15px;
    color: #5c6d7e;
}
#resultCard {
    border: 1px solid #e1e8ef;
    border-radius: 14px;
    background: #f5f8fb;
}
#sectionTitle {
    font-size: 16px;
    font-weight: 600;
}
#fieldLabel {
    color: #344354;
    font-size: 13px;
    font-weight: 500;
}
QTabWidget::pane {
    border: 1px solid #dbe4ee;
    border-radius: 9px;
    background: #ffffff;
}
QTabBar::tab {
    color: #5c6d7e;
    background: #f5f8fb;
    border: 1px solid #dbe4ee;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    min-width: 100px;
    padding: 8px 14px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    color: #255b9f;
    background: #ffffff;
    font-weight: 600;
}
QTabBar::tab:hover {
    color: #255b9f;
}
#metricCard {
    background: #f5f8fb;
    border: 1px solid #e1e8ef;
    border-radius: 8px;
}
#metricValue {
    color: #23446b;
    font-size: 21px;
    font-weight: 650;
}
#chartImage {
    background: #ffffff;
    border: 1px solid #e1e8ef;
    border-radius: 8px;
    padding: 7px;
    color: #5c6d7e;
}
#trainingKey {
    background: #ffffff;
    border: 1px solid #c9d4df;
    border-radius: 7px;
    padding: 0 11px;
}
#trainingKey:focus {
    border-color: #3265a6;
}
QAbstractSpinBox, QComboBox {
    border: 1px solid #c9d4df;
    border-radius: 7px;
    background: #ffffff;
    padding: 0 11px;
    selection-background-color: #dae9fc;
    selection-color: #182b43;
    placeholder-text-color: #657589;
}
QAbstractSpinBox:hover, QComboBox:hover {
    background: #f9fbfd;
    border-color: #aab9ca;
}
QAbstractSpinBox:focus, QComboBox:focus {
    border: 1px solid #3265a6;
}
QAbstractSpinBox QLineEdit {
    border: 0;
    background: transparent;
}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    subcontrol-origin: border;
    width: 28px;
    height: 19px;
    border-left: 1px solid #dbe3eb;
    background: #f4f7fa;
}
QAbstractSpinBox::up-button {
    subcontrol-position: top right;
    border-top-right-radius: 6px;
}
QAbstractSpinBox::down-button {
    subcontrol-position: bottom right;
    border-bottom-right-radius: 6px;
}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {
    background: #e9f1fb;
}
QAbstractSpinBox::up-arrow, QAbstractSpinBox::down-arrow {
    image: none;
}
QComboBox {
    padding-right: 5px;
    combobox-popup: 0;
}
QComboBox::drop-down {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 29px;
    border: 0;
}
QComboBox::down-arrow {
    image: none;
}
QComboBox QAbstractItemView {
    color: #202c39;
    background: #ffffff;
    border: 1px solid #c9d4df;
    selection-background-color: #e9f1fb;
    selection-color: #163b6c;
    outline: 0;
}
QComboBox QAbstractItemView::item {
    padding: 5px 10px;
    min-height: 25px;
}
QAbstractSpinBox:disabled, QComboBox:disabled {
    color: #687888;
    background: #f4f6f8;
}
QComboBox[recommended="true"]:enabled {
    color: #286a48;
    background: #edf7f1;
    border-color: #8ebda3;
}
#submit {
    min-height: 42px;
    border: 1px solid #255b9f;
    border-radius: 8px;
    background: #255b9f;
    color: #ffffff;
    font-weight: 600;
}
#submit:hover {
    background: #1d4e8a;
}
#submit:pressed {
    background: #173e71;
}
#submit:focus {
    border: 2px solid #15355b;
}
#submit:disabled {
    color: #4d657e;
    background: #eaf0f6;
    border-color: #dbe4ee;
}
#message {
    border: 1px solid #efd7cf;
    border-radius: 8px;
    background: #fdf4f0;
    color: #8b3b2a;
    padding: 7px 9px;
    font-size: 13px;
}
#probability {
    color: #23446b;
    font-size: 42px;
    font-weight: 650;
}
#resultCaption, #resultPlace {
    color: #5c6d7e;
    font-size: 13px;
}
#verdict {
    font-size: 20px;
    font-weight: 600;
}
"""
