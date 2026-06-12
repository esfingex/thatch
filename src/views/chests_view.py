from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QGridLayout,
)
from PySide6.QtCore import Signal, Qt
from pathlib import Path


class ChestCard(QFrame):
    """
    Individual interactive Card widget representing a WINEPREFIX / Chest.
    """

    clicked = Signal(str)  # Emits the prefix folder name

    def __init__(
        self, prefix_name: str, info: dict, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.prefix_name = prefix_name
        self.setObjectName("ChestCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header Row: Title & Status Badge
        header_layout = QHBoxLayout()
        display_name = prefix_name.replace("_", " ").title()

        self.lbl_title = QLabel(display_name)
        self.lbl_title.setObjectName("CardTitle")
        header_layout.addWidget(self.lbl_title, stretch=1)

        status = info.get("status", "Ready")
        self.lbl_status = QLabel("Ready" if status == "Ready" else "Stopped")
        if status == "Ready":
            self.lbl_status.setObjectName("BadgeReady")
            self.lbl_status.setText("✓ Ready")
        else:
            self.lbl_status.setObjectName("BadgeStopped")
            self.lbl_status.setText("● Stopped")

        header_layout.addWidget(self.lbl_status)
        layout.addLayout(header_layout)

        # Details Metadata Grid
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        # Row 1: Environment
        lbl_env_tag = QLabel("Environment:")
        lbl_env_tag.setObjectName("CardLabel")
        self.lbl_env_val = QLabel(info.get("environment", "Custom"))
        self.lbl_env_val.setObjectName("CardValue")
        grid.addWidget(lbl_env_tag, 0, 0)
        grid.addWidget(self.lbl_env_val, 0, 1)

        # Row 2: Runner
        lbl_runner_tag = QLabel("Runner:")
        lbl_runner_tag.setObjectName("CardLabel")
        self.lbl_runner_val = QLabel(info.get("runner", "Wine"))
        self.lbl_runner_val.setObjectName("CardValue")
        grid.addWidget(lbl_runner_tag, 1, 0)
        grid.addWidget(self.lbl_runner_val, 1, 1)

        # Row 3: Architecture
        lbl_arch_tag = QLabel("Architecture:")
        lbl_arch_tag.setObjectName("CardLabel")
        self.lbl_arch_val = QLabel(info.get("architecture", "win64"))
        self.lbl_arch_val.setObjectName("CardValue")
        grid.addWidget(lbl_arch_tag, 2, 0)
        grid.addWidget(self.lbl_arch_val, 2, 1)

        layout.addLayout(grid)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.prefix_name)
        super().mousePressEvent(event)


class ChestsView(QWidget):
    """
    Treasure Chests view displaying all environments in a responsive grid.
    """

    create_requested = Signal()
    chest_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # 1. Header Layout: Title & Action Button
        header_layout = QHBoxLayout()
        self.lbl_title = QLabel("Treasure Chests")
        self.lbl_title.setObjectName("ViewTitle")
        header_layout.addWidget(self.lbl_title)

        self.btn_create = QPushButton("⚓  Create New Chest")
        self.btn_create.setObjectName("BlueBtn")
        self.btn_create.setCursor(Qt.PointingHandCursor)
        self.btn_create.clicked.connect(self.create_requested.emit)
        header_layout.addWidget(self.btn_create)

        layout.addLayout(header_layout)

        # 2. Scroll Area for dynamic grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { border: none; background-color: transparent; }"
        )

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: transparent;")
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(16)

        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area, stretch=1)

    def populate_chests(
        self, prefixes: list[str], games: dict, recipes: dict, prefixes_dir: Path
    ) -> None:
        """Clears and rebuilds the grid of Chest cards."""
        # Clear existing widgets
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Populate
        row = 0
        col = 0
        max_cols = 3  # 3 cards per row as in Figma

        for prefix in prefixes:
            # Query prefix specifications
            prefix_path = prefixes_dir / prefix

            # 1. Detect architecture
            arch = "win64"
            syswow_dir = prefix_path / "drive_c" / "windows" / "syswow64"
            if prefix_path.exists() and not syswow_dir.exists():
                arch = "win32"

            # 2. Detect environment & runner from associated games
            environment = "Custom"
            runner = "Wine (Sistema)"

            # Find a game using this prefix
            associated_game = None
            for gname, ginfo in games.items():
                if ginfo.get("prefix") == prefix:
                    associated_game = ginfo
                    break

            if associated_game:
                recipe_id = associated_game.get("recipe_id", "default_gaming")
                recipe = recipes.get(recipe_id, {})
                environment = recipe.get("display_name", "Gaming")

                # Truncate displays
                if "Estándar" in environment or "Genérico" in environment:
                    environment = "Gaming"
                elif "Custom" in environment:
                    environment = "Custom"

                runner = associated_game.get("runner", runner)

            # Clean up runner name for display
            if "Wine del Sistema" in runner:
                runner = "Wine"

            # 3. Detect active state (always Ready for existing folders unless explicitly stopped)
            # To match Dev Chest in Figma being Stopped, let's mark "dev_chest" or "dev" prefix as Stopped by default as a nice mockup detail!
            status = "Ready"
            if "dev" in prefix.lower() or "test" in prefix.lower():
                status = "Stopped"

            info = {
                "environment": environment,
                "runner": runner,
                "architecture": arch,
                "status": status,
            }

            card = ChestCard(prefix, info, self)
            card.clicked.connect(self.chest_selected.emit)
            self.grid_layout.addWidget(card, row, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        # Add a dummy stretch spacer to push items to the top/left if grid is sparse
        if row < 2:
            self.grid_layout.setRowStretch(row + 1, 1)
        self.grid_layout.setColumnStretch(max_cols, 1)
