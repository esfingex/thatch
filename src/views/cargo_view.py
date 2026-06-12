from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QFrame,
    QGridLayout,
    QPushButton,
    QInputDialog,
    QMessageBox,
)
from PySide6.QtCore import Signal, Slot, Qt
from pathlib import Path


class MapCard(QFrame):
    """
    Styled map card displaying dynamically loaded JSON recipes,
    their respective winetricks injection targets, and direct application hooks.
    """

    install_clicked = Signal(str, str)  # Emits: display_name, recipe_id
    delete_clicked = Signal(str, str)  # Emits: display_name, recipe_id

    def __init__(
        self, recipe_id: str, recipe_data: dict, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.recipe_id = recipe_id
        self.recipe_data = recipe_data
        self.setObjectName("AppCard")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header Row: Title & Badge
        header = QHBoxLayout()
        display_name = recipe_data.get(
            "display_name", recipe_id.replace("_", " ").title()
        )
        lbl_title = QLabel(display_name)
        lbl_title.setObjectName("CardTitle")
        header.addWidget(lbl_title, stretch=1)

        lbl_badge = QLabel("⚓ Mapa")
        lbl_badge.setObjectName("BadgePlatinum")
        header.addWidget(lbl_badge)
        layout.addLayout(header)

        # Description
        lbl_desc = QLabel(
            recipe_data.get("description", "Receta JSON autoportante para compartir.")
        )
        lbl_desc.setStyleSheet("color: #71717a; font-size: 12px;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc, stretch=1)

        # Display required verbs
        verbs = recipe_data.get("required_verbs", [])
        verbs_text = (
            f"Inyecta: {', '.join(verbs)}"
            if verbs
            else "Sin dependencias de winetricks"
        )
        lbl_verbs = QLabel(verbs_text)
        lbl_verbs.setStyleSheet("color: #8e8e93; font-size: 11px; font-style: italic;")
        lbl_verbs.setWordWrap(True)
        layout.addWidget(lbl_verbs)

        # Bottom Row: Category & Install Button
        bottom = QHBoxLayout()
        lbl_tag = QLabel("Receta JSON")
        lbl_tag.setObjectName("AppTag")
        bottom.addWidget(lbl_tag)
        bottom.addStretch(1)

        self.btn_install = QPushButton("Aplicar Mapa")
        self.btn_install.setObjectName("BlueBtn")
        self.btn_install.setCursor(Qt.PointingHandCursor)
        self.btn_install.clicked.connect(
            lambda: self.install_clicked.emit(display_name, self.recipe_id)
        )
        bottom.addWidget(self.btn_install)

        self.btn_delete = QPushButton("🗑️")
        self.btn_delete.setObjectName("RedBtn")
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setToolTip("Eliminar este mapa")
        self.btn_delete.clicked.connect(
            lambda: self.delete_clicked.emit(display_name, self.recipe_id)
        )
        bottom.addWidget(self.btn_delete)

        layout.addLayout(bottom)


class MapasView(QWidget):
    """
    Mapas del Tesoro View that loads all shareable JSON configs inside config/recipes/
    and lets the user selectively inject only the missing verbs.
    """

    install_requested = Signal(str, str, str)  # display_name, recipe_id, target_prefix
    map_deleted = Signal()  # Emitted when a map is deleted to refresh data

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.active_prefixes = []
        self.recipes = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # 1. Header Layout
        header = QVBoxLayout()
        header.setSpacing(4)
        lbl_title = QLabel("Mapas del Tesoro")
        lbl_title.setObjectName("ViewTitle")
        lbl_subtitle = QLabel(
            "Configuraciones y recetas JSON compartibles en config/recipes/"
        )
        lbl_subtitle.setStyleSheet("color: #71717a; font-size: 13px;")
        header.addWidget(lbl_title)
        header.addWidget(lbl_subtitle)
        layout.addLayout(header)

        # 2. Search bar
        filter_layout = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔎 Buscar mapa de receta...")
        self.txt_search.textChanged.connect(self._on_filters_changed)
        filter_layout.addWidget(self.txt_search)
        layout.addLayout(filter_layout)

        # 3. Cards Scroll Area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(
            "QScrollArea { border: none; background-color: transparent; }"
        )

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: transparent;")
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(16)

        scroll_area.setWidget(self.scroll_content)
        layout.addWidget(scroll_area, stretch=1)

        # 4. Description Info Card
        about_card = QFrame()
        about_card.setObjectName("PrefCard")
        about_layout = QVBoxLayout(about_card)
        about_layout.setSpacing(8)

        lbl_about_title = QLabel("🗺️ Sobre los Mapas del Tesoro")
        lbl_about_title.setObjectName("CardTitle")
        about_layout.addWidget(lbl_about_title)

        lbl_about_desc = QLabel(
            "Los mapas son archivos JSON autoportantes y compartibles. "
            "Al aplicar un mapa sobre un cofre (WINEPREFIX), Thatch leerá las dependencias necesarias de Winetricks, "
            "las comparará con las ya inyectadas para saltarse las existentes e inyectará de forma secuencial "
            "únicamente las dependencias faltantes, optimizando la instalación y previniendo archivos corruptos o redundantes."
        )
        lbl_about_desc.setStyleSheet(
            "color: #71717a; font-size: 12px; line-height: 18px;"
        )
        lbl_about_desc.setWordWrap(True)
        about_layout.addWidget(lbl_about_desc)

        layout.addWidget(about_card)

        # Initial draw
        self.populate_maps([], {})

    def populate_maps(self, prefixes: list[str], recipes: dict) -> None:
        """Saves current active prefixes and recipes, drawing the grid."""
        self.active_prefixes = prefixes
        self.recipes = recipes
        self._render_grid()

    def _render_grid(self) -> None:
        """Clears and renders the grid items based on active search."""
        # Clear layout
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        search_query = self.txt_search.text().strip().lower()

        filtered = []
        for recipe_id, recipe in self.recipes.items():
            display_name = recipe.get("display_name", recipe_id)
            desc = recipe.get("description", "")

            # Filter matches
            match_search = (
                not search_query
                or search_query in display_name.lower()
                or search_query in desc.lower()
            )
            if match_search:
                filtered.append((recipe_id, recipe))

        # Draw filtered grid
        row = 0
        col = 0
        max_cols = 3

        for recipe_id, recipe in filtered:
            card = MapCard(recipe_id, recipe, self)
            card.install_clicked.connect(self._on_install_clicked)
            card.delete_clicked.connect(self._on_delete_clicked)
            self.grid_layout.addWidget(card, row, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        # Add stretch
        if row < 2:
            self.grid_layout.setRowStretch(row + 1, 1)
        self.grid_layout.setColumnStretch(max_cols, 1)

    @Slot(str, str)
    def _on_install_clicked(self, app_name: str, recipe_id: str) -> None:
        """Prompts user to select a target chest before initiating setup."""
        if not self.active_prefixes:
            QMessageBox.warning(
                self,
                "No Chests Found",
                "¡Necesitas crear al menos un cofre antes de aplicarle un mapa!",
            )
            return

        # Dialog selection list of prefixes
        item, ok = QInputDialog.getItem(
            self,
            "Seleccionar Cofre Destino",
            f"Selecciona el cofre para aplicar el mapa '{app_name}':",
            self.active_prefixes,
            0,
            False,
        )
        if ok and item:
            self.install_requested.emit(app_name, recipe_id, item)

    @Slot(str, str)
    def _on_delete_clicked(self, app_name: str, recipe_id: str) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmar Eliminación",
            f"¿Estás seguro de que quieres eliminar permanentemente el mapa '{app_name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            file_path = Path("config/recipes") / f"{recipe_id}.json"
            try:
                if file_path.exists():
                    file_path.unlink()
                QMessageBox.information(
                    self, "Eliminado", "Mapa eliminado correctamente."
                )
                self.map_deleted.emit()
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"No se pudo eliminar el mapa:\n{e}"
                )

    @Slot()
    def _on_filters_changed(self) -> None:
        self._render_grid()
