from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QButtonGroup,
    QWidget,
)
from PySide6.QtCore import Signal, Qt, Slot
from i18n import _


class UnifiedSidebar(QFrame):
    """
    Sleek, unified sidebar navigation component matching Figma mockups.
    Manages active views: Chests, Cargo, Wine Runners, and Preferences.
    """

    view_changed = Signal(str)  # Emits: "chests", "cargo", "runners", "preferences"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarFrame")
        self.setFixedWidth(200)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 20, 12, 20)
        layout.setSpacing(8)

        # 1. Header Title
        self.lbl_title = QLabel(_("sidebar_title"))
        self.lbl_title.setObjectName("SidebarTitle")
        self.lbl_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.lbl_title)

        # Button Group to make buttons mutually exclusive
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        # 2. Chests Navigation Button
        self.btn_chests = QPushButton(_("sidebar_chests"))
        self.btn_chests.setObjectName("SidebarBtn")
        self.btn_chests.setCheckable(True)
        self.btn_chests.setChecked(True)
        self.btn_chests.setCursor(Qt.PointingHandCursor)
        self.btn_chests.clicked.connect(lambda: self._on_btn_clicked("chests"))
        self.btn_group.addButton(self.btn_chests)
        layout.addWidget(self.btn_chests)

        # 3. Cargo Navigation Button
        self.btn_cargo = QPushButton(_("sidebar_cargo"))
        self.btn_cargo.setObjectName("SidebarBtn")
        self.btn_cargo.setCheckable(True)
        self.btn_cargo.setCursor(Qt.PointingHandCursor)
        self.btn_cargo.clicked.connect(lambda: self._on_btn_clicked("cargo"))
        self.btn_group.addButton(self.btn_cargo)
        layout.addWidget(self.btn_cargo)

        # 4. Wine Runners Navigation Button
        self.btn_runners = QPushButton(_("sidebar_runners"))
        self.btn_runners.setObjectName("SidebarBtn")
        self.btn_runners.setCheckable(True)
        self.btn_runners.setCursor(Qt.PointingHandCursor)
        self.btn_runners.clicked.connect(lambda: self._on_btn_clicked("runners"))
        self.btn_group.addButton(self.btn_runners)
        layout.addWidget(self.btn_runners)

        # 5. Recipes Navigation Button
        self.btn_recipes = QPushButton(_("sidebar_recipes"))
        self.btn_recipes.setObjectName("SidebarBtn")
        self.btn_recipes.setCheckable(True)
        self.btn_recipes.setCursor(Qt.PointingHandCursor)
        self.btn_recipes.clicked.connect(lambda: self._on_btn_clicked("recipes"))
        self.btn_group.addButton(self.btn_recipes)
        layout.addWidget(self.btn_recipes)

        # Spacer to push preferences to the bottom
        layout.addStretch(1)

        # 5. Preferences Button (bottom)
        self.btn_prefs = QPushButton(_("sidebar_preferences"))
        self.btn_prefs.setObjectName("SidebarBtn")
        self.btn_prefs.setCheckable(True)
        self.btn_prefs.setCursor(Qt.PointingHandCursor)
        self.btn_prefs.clicked.connect(lambda: self._on_btn_clicked("preferences"))
        self.btn_group.addButton(self.btn_prefs)
        layout.addWidget(self.btn_prefs)

        # 6. Version indicator (Sleek minimalist footer)
        self.lbl_version = QLabel("v1.0.1")
        self.lbl_version.setStyleSheet(
            "color: #48484a; font-size: 10px; font-weight: bold; margin-left: 16px; margin-top: 8px;"
        )
        layout.addWidget(self.lbl_version)

    @Slot(str)
    def _on_btn_clicked(self, view_name: str) -> None:
        """Emits the view change signal when a button is clicked."""
        self.view_changed.emit(view_name)

    def set_active_view(self, view_name: str) -> None:
        """Programmatically sets the active button corresponding to the view name."""
        self.btn_group.blockSignals(True)
        if view_name == "chests":
            self.btn_chests.setChecked(True)
        elif view_name == "cargo":
            self.btn_cargo.setChecked(True)
        elif view_name == "runners":
            self.btn_runners.setChecked(True)
        elif view_name == "recipes":
            self.btn_recipes.setChecked(True)
        elif view_name == "preferences":
            self.btn_prefs.setChecked(True)
        self.btn_group.blockSignals(False)

    def retranslate(self) -> None:
        """Cascades translation updates to all sidebar elements."""
        self.lbl_title.setText(_("sidebar_title"))
        self.btn_chests.setText(_("sidebar_chests"))
        self.btn_cargo.setText(_("sidebar_cargo"))
        self.btn_runners.setText(_("sidebar_runners"))
        self.btn_recipes.setText(_("sidebar_recipes"))
        self.btn_prefs.setText(_("sidebar_preferences"))
