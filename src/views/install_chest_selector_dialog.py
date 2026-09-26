from pathlib import Path
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
)
from PySide6.QtCore import Qt
from i18n import _, ACTIVE_LANG


class InstallChestSelectorDialog(QDialog):
    """
    Modal dialog presented when launching an installer file via "Instalar con Thatch"
    or CLI --install argument. Allows the user to choose an existing chest or create a new one.
    """

    def __init__(
        self,
        installer_path: str,
        chests: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.installer_path = installer_path
        self.chests = chests
        self.selected_chest: str | None = None
        self.request_create_new: bool = False

        self.setWindowTitle(_("install_selector_title"))
        self.setMinimumWidth(480)
        self.setMaximumWidth(600)
        self.resize(520, 440)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #121214;
                color: #ffffff;
            }
            QFrame#CardFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
            }
            QFrame#ChestCard {
                background-color: #1f1f23;
                border: 1px solid #2d2d34;
                border-radius: 8px;
            }
            QFrame#ChestCard:hover {
                border-color: #3b82f6;
                background-color: #242429;
            }
            QPushButton#InstallBtn {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton#InstallBtn:hover {
                background-color: #1d4ed8;
            }
            QPushButton#CreateBtn {
                background-color: #059669;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton#CreateBtn:hover {
                background-color: #047857;
            }
            QPushButton#CancelBtn {
                background-color: #27272a;
                color: #a1a1aa;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton#CancelBtn:hover {
                background-color: #3f3f46;
                color: #ffffff;
            }
            """
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # 1. Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)

        lbl_title = QLabel(_("install_selector_title"))
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(lbl_title)

        lbl_subtitle = QLabel(_("install_selector_subtitle"))
        lbl_subtitle.setStyleSheet("font-size: 13px; color: #a1a1aa;")
        header_layout.addWidget(lbl_subtitle)

        main_layout.addLayout(header_layout)

        # 2. Executable Info Frame
        exe_file = Path(installer_path)
        file_frame = QFrame()
        file_frame.setObjectName("CardFrame")
        file_layout = QHBoxLayout(file_frame)
        file_layout.setContentsMargins(14, 10, 14, 10)

        lbl_file_icon = QLabel("💿")
        lbl_file_icon.setStyleSheet("font-size: 20px;")
        file_layout.addWidget(lbl_file_icon)

        file_text_layout = QVBoxLayout()
        file_text_layout.setSpacing(2)

        lbl_file_name = QLabel(exe_file.name)
        lbl_file_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #60a5fa;")
        lbl_file_name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        file_text_layout.addWidget(lbl_file_name)

        lbl_file_path = QLabel(str(exe_file.parent))
        lbl_file_path.setStyleSheet("font-size: 11px; color: #71717a;")
        lbl_file_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        file_text_layout.addWidget(lbl_file_path)

        file_layout.addLayout(file_text_layout, stretch=1)
        main_layout.addWidget(file_frame)

        # 3. Chests List (Scroll Area)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(10)

        if chests:
            for chest_name in chests:
                card = QFrame()
                card.setObjectName("ChestCard")
                c_layout = QHBoxLayout(card)
                c_layout.setContentsMargins(14, 12, 14, 12)

                lbl_chest_icon = QLabel("🏴‍☠️")
                lbl_chest_icon.setStyleSheet("font-size: 18px;")
                c_layout.addWidget(lbl_chest_icon)

                lbl_name = QLabel(chest_name)
                lbl_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
                c_layout.addWidget(lbl_name, stretch=1)

                btn_install = QPushButton(_("btn_install_here"))
                btn_install.setObjectName("InstallBtn")
                btn_install.setCursor(Qt.PointingHandCursor)
                btn_install.clicked.connect(lambda _, c=chest_name: self._select_chest(c))
                c_layout.addWidget(btn_install)

                scroll_layout.addWidget(card)
        else:
            lbl_no_chests = QLabel(_("no_chests_found"))
            lbl_no_chests.setStyleSheet(
                "color: #f59e0b; font-size: 13px; font-weight: bold; margin: 20px 0;"
            )
            lbl_no_chests.setAlignment(Qt.AlignCenter)
            scroll_layout.addWidget(lbl_no_chests)

        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, stretch=1)

        # 4. Footer Buttons
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(10)

        btn_create = QPushButton(_("btn_create_new_chest"))
        btn_create.setObjectName("CreateBtn")
        btn_create.setCursor(Qt.PointingHandCursor)
        btn_create.clicked.connect(self._create_new_chest)
        footer_layout.addWidget(btn_create)

        footer_layout.addStretch(1)

        btn_cancel = QPushButton("Cancelar" if ACTIVE_LANG == "es" else "Cancel")
        btn_cancel.setObjectName("CancelBtn")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(btn_cancel)

        main_layout.addLayout(footer_layout)

    def _select_chest(self, chest_name: str) -> None:
        self.selected_chest = chest_name
        self.request_create_new = False
        self.accept()

    def _create_new_chest(self) -> None:
        self.selected_chest = None
        self.request_create_new = True
        self.accept()
