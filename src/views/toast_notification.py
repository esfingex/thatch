from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget
from PySide6.QtCore import Qt, QTimer, QPoint


class ToastNotification(QFrame):
    """
    Animated snackbar / toast notification shown at the bottom right
    of the main window, matching Figma mockups.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ToastFrame")
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Checkmark Icon
        self.lbl_icon = QLabel("✅")
        self.lbl_icon.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.lbl_icon)

        # Message label
        self.lbl_message = QLabel("")
        self.lbl_message.setStyleSheet(
            "color: #e4e4e7; font-size: 13px; font-weight: bold;"
        )
        layout.addWidget(self.lbl_message, stretch=1)

        # Dismiss button
        self.btn_dismiss = QPushButton("Desestimar")
        self.btn_dismiss.setStyleSheet(
            "background-color: transparent; border: none; color: #a1a1aa; "
            "font-size: 12px; font-weight: bold; padding: 2px 6px;"
        )
        self.btn_dismiss.setCursor(Qt.PointingHandCursor)
        self.btn_dismiss.clicked.connect(self.hide)
        layout.addWidget(self.btn_dismiss)

        # Timer for auto-dismiss
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

        self.hide()

    def show_message(self, message: str, duration_ms: int = 5000) -> None:
        """Sets the text, restarts the auto-hide timer, and shows the toast."""
        self.lbl_message.setText(message)
        self.timer.stop()
        self.timer.start(duration_ms)
        self.show()
        self.raise_()
        self.adjust_position()

    def adjust_position(self) -> None:
        """Positions the toast in the bottom-right corner of the parent widget."""
        if not self.parentWidget():
            return

        # Position 20px from bottom, 20px from right
        parent_rect = self.parentWidget().rect()
        self.adjustSize()

        x = parent_rect.width() - self.width() - 20
        y = parent_rect.height() - self.height() - 20

        self.move(QPoint(x, y))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.adjust_position()
