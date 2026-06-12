# views/library_sidebar.py
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
)
from PySide6.QtCore import Slot, Signal


class LibrarySidebar(QWidget):
    """
    Sidebar navigation microcomponent controlling library listings,
    view switching, and generic creation/deletion requests.
    """

    selection_changed = Signal(str, str)  # current_name, view_mode
    add_requested = Signal(str)  # view_mode
    remove_requested = Signal(str, str)  # name, view_mode
    zeus_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # App Header
        header_lbl = QLabel("🏴‍☠️ THATCH")
        header_lbl.setStyleSheet(
            "font-weight: 900; font-size: 20px; color: #00e676; letter-spacing: 1px; padding: 4px;"
        )
        layout.addWidget(header_lbl)

        # View Switcher (Juegos vs. Entornos)
        self.current_view = "games"
        switcher_layout = QHBoxLayout()
        switcher_layout.setSpacing(6)

        self.btn_view_games = QPushButton("🎮 Juegos")
        self.btn_view_games.setStyleSheet(
            "background-color: #1e291e; color: #00e676; border: 1px solid #00e676; font-weight: bold;"
        )
        self.btn_view_games.clicked.connect(self._on_switch_to_games)
        switcher_layout.addWidget(self.btn_view_games, stretch=1)

        self.btn_view_envs = QPushButton("📦 Entornos")
        self.btn_view_envs.setStyleSheet(
            "background-color: #202024; color: #a1a1aa; border: 1px solid #2d2d34;"
        )
        self.btn_view_envs.clicked.connect(self._on_switch_to_envs)
        switcher_layout.addWidget(self.btn_view_envs, stretch=1)

        layout.addLayout(switcher_layout)

        # Main listings
        self.list_items = QListWidget()
        self.list_items.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.list_items)

        # Generic Actions (Add / Remove)
        action_btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Reclutar Juego")
        self.btn_add.setStyleSheet(
            "background-color: #202024; color: #00e676; border: 1px solid #2d2d34;"
        )
        self.btn_add.clicked.connect(self._on_add_clicked)
        action_btn_layout.addWidget(self.btn_add)

        self.btn_remove = QPushButton("Borrar")
        self.btn_remove.setStyleSheet("color: #ff1744; border: 1px solid #2d2d34;")
        self.btn_remove.clicked.connect(self._on_remove_clicked)
        action_btn_layout.addWidget(self.btn_remove)
        layout.addLayout(action_btn_layout)

        # Bottom tools (Zeus Installer & Settings)
        bottom_lay = QHBoxLayout()
        self.btn_zeus = QPushButton("Instalador Zeus")
        self.btn_zeus.setStyleSheet("color: #00e5ff; border: 1px solid #282830;")
        self.btn_zeus.clicked.connect(self.zeus_requested.emit)
        bottom_lay.addWidget(self.btn_zeus)

        self.btn_settings = QPushButton("Ajustes")
        self.btn_settings.clicked.connect(self.settings_requested.emit)
        bottom_lay.addWidget(self.btn_settings)
        layout.addLayout(bottom_lay)

    @Slot()
    def _on_switch_to_games(self) -> None:
        self.current_view = "games"
        self.btn_view_games.setStyleSheet(
            "background-color: #1e291e; color: #00e676; border: 1px solid #00e676; font-weight: bold;"
        )
        self.btn_view_envs.setStyleSheet(
            "background-color: #202024; color: #a1a1aa; border: 1px solid #2d2d34;"
        )
        self.btn_add.setText("Reclutar Juego")
        self.btn_remove.setText("Borrar Juego")
        self.btn_zeus.show()
        self.selection_changed.emit("", "games")

    @Slot()
    def _on_switch_to_envs(self) -> None:
        self.current_view = "envs"
        self.btn_view_envs.setStyleSheet(
            "background-color: #1e291e; color: #00e5ff; border: 1px solid #00e5ff; font-weight: bold;"
        )
        self.btn_view_games.setStyleSheet(
            "background-color: #202024; color: #a1a1aa; border: 1px solid #2d2d34;"
        )
        self.btn_add.setText("Crear Entorno")
        self.btn_remove.setText("Borrar Entorno")
        self.btn_zeus.hide()
        self.selection_changed.emit("", "envs")

    @Slot()
    def _on_selection_changed(self) -> None:
        item = self.list_items.currentItem()
        name = item.text() if item else ""
        self.selection_changed.emit(name, self.current_view)

    @Slot()
    def _on_add_clicked(self) -> None:
        self.add_requested.emit(self.current_view)

    @Slot()
    def _on_remove_clicked(self) -> None:
        item = self.list_items.currentItem()
        if item:
            self.remove_requested.emit(item.text(), self.current_view)

    def populate(self, items: list[str], select_name: str | None = None) -> None:
        self.list_items.blockSignals(True)
        self.list_items.clear()
        self.list_items.addItems(items)
        self.list_items.blockSignals(False)

        if select_name:
            for i in range(self.list_items.count()):
                if self.list_items.item(i).text() == select_name:
                    self.list_items.setCurrentRow(i)
                    break
        elif len(items) > 0:
            self.list_items.setCurrentRow(0)

        self._on_selection_changed()

    def set_ui_locked(self, locked: bool) -> None:
        self.btn_view_games.setEnabled(not locked)
        self.btn_view_envs.setEnabled(not locked)
        self.btn_add.setEnabled(not locked)
        self.btn_remove.setEnabled(not locked)
        self.btn_zeus.setEnabled(not locked)
        self.btn_settings.setEnabled(not locked)
        self.list_items.setEnabled(not locked)
