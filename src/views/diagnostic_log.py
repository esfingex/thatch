# views/diagnostic_log.py
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QProgressBar,
    QWidget,
)
from PySide6.QtCore import Qt


class DiagnosticLogCard(QFrame):
    """
    QtWidgets microcomponent displaying real-time execution outputs
    and progress status of background tasks.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CardFrame")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        card_lbl = QLabel("Bitácora de Diagnóstico (Recetas):")
        card_lbl.setObjectName("CardTitle")
        layout.addWidget(card_lbl)

        self.console_log = QTextEdit()
        self.console_log.setObjectName("ConsoleLog")
        self.console_log.setReadOnly(True)
        self.console_log.setMinimumHeight(140)
        self.console_log.setMaximumHeight(220)
        self.console_log.hide()
        layout.addWidget(self.console_log)

        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_bar)

    def show_console(self) -> None:
        self.console_log.clear()
        self.console_log.show()

    def hide_console(self) -> None:
        self.console_log.hide()

    def append_log(self, text: str) -> None:
        self.console_log.append(text)

    def set_progress(self, current: int, total: int) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)

    def set_busy_state(self, message: str) -> None:
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFormat(message)
