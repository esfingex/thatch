from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import QApplication

STYLESHEET = """
QMainWindow {
    background-color: #0f0f13;
}

/* Sidebar Styling */
QFrame#SidebarFrame {
    background-color: #15151a;
    border-right: 1px solid #1f1f27;
}

QLabel#SidebarTitle {
    color: #e2e2e9;
    font-size: 22px;
    font-weight: 900;
    letter-spacing: 1px;
    padding: 16px;
}

QPushButton#SidebarBtn {
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 12px 18px;
    margin: 2px 12px;
    color: #8f8f9d;
    font-size: 14px;
    font-weight: 600;
    text-align: left;
}
QPushButton#SidebarBtn:hover {
    background-color: #1f1f27;
    color: #ffffff;
}
QPushButton#SidebarBtn:checked {
    background-color: #272732;
    color: #4da6ff;
    border-left: 3px solid #4da6ff;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
}

/* Main Content Area */
QLabel#ViewTitle {
    color: #ffffff;
    font-size: 26px;
    font-weight: bold;
    letter-spacing: 0.5px;
}

/* Flat Cards & Panels */
QFrame#ChestCard, QFrame#AppCard, QFrame#DetailCard, QFrame#PrefCard {
    background-color: #1a1a21;
    border: 1px solid #24242e;
    border-radius: 12px;
    padding: 20px;
}
QFrame#ChestCard:hover, QFrame#AppCard:hover {
    background-color: #1e1e26;
    border: 1px solid #333342;
}

QLabel#CardTitle {
    color: #ffffff;
    font-size: 16px;
    font-weight: bold;
}

QLabel#CardLabel {
    color: #8f8f9d;
    font-size: 13px;
}

QLabel#CardValue {
    color: #e2e2e9;
    font-size: 13px;
    font-weight: 500;
}

/* Badges */
QLabel#BadgeReady {
    background-color: rgba(48, 209, 88, 0.15);
    color: #30d158;
    border: 1px solid rgba(48, 209, 88, 0.3);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 800;
}

QLabel#BadgeStopped {
    background-color: rgba(142, 142, 147, 0.1);
    color: #8e8e93;
    border: 1px solid rgba(142, 142, 147, 0.2);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 800;
}

QLabel#AppTag {
    background-color: #24242e;
    color: #b0b0bc;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: bold;
}

/* Inputs & Comboboxes */
QLineEdit, QComboBox {
    background-color: #15151a;
    border: 1px solid #2a2a35;
    border-radius: 8px;
    padding: 10px 14px;
    color: #ffffff;
    font-size: 13px;
}
QLineEdit:focus, QComboBox:hover {
    border: 1px solid #4da6ff;
    background-color: #1a1a21;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #8f8f9d;
    margin-top: 2px;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #1a1a21;
    border: 1px solid #2a2a35;
    border-radius: 8px;
    selection-background-color: #4da6ff;
    selection-color: #ffffff;
    color: #ffffff;
    outline: none;
}

/* Modern Rounded Buttons */
QPushButton {
    background-color: #24242e;
    border: 1px solid #2a2a35;
    border-radius: 8px;
    padding: 10px 16px;
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #2a2a35;
    border: 1px solid #333342;
}
QPushButton:pressed {
    background-color: #1f1f27;
}
QPushButton:disabled {
    background-color: #15151a;
    color: #555566;
    border: 1px solid #1f1f27;
}

/* Accent Buttons */
QPushButton#BlueBtn {
    background-color: #2188ff;
    color: #ffffff;
    border: none;
    font-weight: bold;
}
QPushButton#BlueBtn:hover {
    background-color: #3192ff;
}

/* Orange/Run Buttons */
QPushButton#OrangeBtn {
    background-color: #ff7b00;
    color: #ffffff;
    border: none;
    font-weight: bold;
}
QPushButton#OrangeBtn:hover {
    background-color: #ff8c1a;
}

/* Red/Delete Buttons */
QPushButton#RedBtn {
    background-color: #e53935;
    color: #ffffff;
    border: none;
    font-weight: bold;
}
QPushButton#RedBtn:hover {
    background-color: #f44336;
}
QPushButton#RedBtnText {
    background-color: transparent;
    border: 1px solid #3a2222;
    color: #ff5252;
}
QPushButton#RedBtnText:hover {
    background-color: rgba(229, 57, 53, 0.1);
    border: 1px solid #e53935;
}

/* Tab buttons in Chest Details */
QPushButton#TabBtn {
    background-color: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0px;
    padding: 10px 14px;
    color: #8f8f9d;
    font-size: 14px;
    font-weight: 600;
}
QPushButton#TabBtn:hover {
    color: #ffffff;
    background-color: rgba(255, 255, 255, 0.05);
}
QPushButton#TabBtn:checked {
    color: #4da6ff;
    border-bottom: 2px solid #4da6ff;
}

/* Wizard Stepper Stepper Circles */
QLabel#StepCircleActive {
    background-color: #4da6ff;
    color: #ffffff;
    border: none;
    border-radius: 14px;
    font-weight: bold;
    font-size: 13px;
    min-width: 28px;
    min-height: 28px;
    max-width: 28px;
    max-height: 28px;
    alignment: center;
}

QLabel#StepCircleInactive {
    background-color: #1f1f27;
    color: #8f8f9d;
    border: 1px solid #2a2a35;
    border-radius: 14px;
    font-weight: bold;
    font-size: 13px;
    min-width: 28px;
    min-height: 28px;
    max-width: 28px;
    max-height: 28px;
    alignment: center;
}

QLabel#StepLine {
    background-color: #2a2a35;
    max-height: 2px;
    min-height: 2px;
}

/* ScrollBars */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 10px;
    margin: 2px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.15);
    min-height: 30px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(255, 255, 255, 0.3);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Toast/Snackbar Frame */
QFrame#ToastFrame {
    background-color: #1e1e26;
    border: 1px solid #2a2a35;
    border-radius: 8px;
    padding: 10px 16px;
}

/* Progress bar */
QProgressBar {
    border: none;
    border-radius: 6px;
    text-align: center;
    background-color: #1f1f27;
    color: #ffffff;
    font-weight: bold;
    font-size: 12px;
    height: 18px;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #4da6ff, stop: 1 #2188ff);
    border-radius: 6px;
}

/* List Widgets */
QListWidget {
    background-color: #15151a;
    border: 1px solid #24242e;
    border-radius: 8px;
    padding: 6px;
    color: #e2e2e9;
    outline: none;
}
QListWidget::item {
    background-color: #1a1a21;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 10px;
    margin-bottom: 6px;
    color: #e2e2e9;
}
QListWidget::item:hover {
    background-color: #1e1e26;
}
QListWidget::item:selected {
    background-color: rgba(77, 166, 255, 0.1);
    border: 1px solid #4da6ff;
    color: #4da6ff;
}

/* Checkboxes */
QCheckBox {
    color: #e2e2e9;
    font-size: 13px;
    spacing: 10px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #333342;
    border-radius: 4px;
    background-color: #15151a;
}
QCheckBox::indicator:hover {
    border: 1px solid #4da6ff;
}
QCheckBox::indicator:checked {
    background-color: #4da6ff;
    border: 1px solid #4da6ff;
}

/* Console Log */
QTextEdit#ConsoleLog {
    background-color: #0b0b0e;
    border: 1px solid #1f1f27;
    border-radius: 8px;
    color: #00ff66;
    font-family: 'JetBrains Mono', 'Courier New', monospace;
    font-size: 12px;
    padding: 12px;
}
"""


def apply_theme(app: QApplication) -> None:
    """Applies the premium, sleek dark theme to the Qt App."""
    font = QFont("Inter", 10)
    if not font.exactMatch():
        font = QFont("Segoe UI", 10)
    app.setFont(font)

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#0f0f13"))
    palette.setColor(QPalette.WindowText, QColor("#ffffff"))
    palette.setColor(QPalette.Base, QColor("#15151a"))
    palette.setColor(QPalette.AlternateBase, QColor("#0f0f13"))
    palette.setColor(QPalette.ToolTipBase, QColor("#1a1a21"))
    palette.setColor(QPalette.ToolTipText, QColor("#ffffff"))
    palette.setColor(QPalette.Text, QColor("#e2e2e9"))
    palette.setColor(QPalette.Button, QColor("#24242e"))
    palette.setColor(QPalette.ButtonText, QColor("#ffffff"))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Highlight, QColor("#4da6ff"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    app.setStyleSheet(STYLESHEET)
