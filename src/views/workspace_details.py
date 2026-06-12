# views/workspace_details.py
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QFormLayout,
    QComboBox,
)
from PySide6.QtCore import Slot, Signal, Qt

from .diagnostic_log import DiagnosticLogCard


class WorkspaceDetails(QWidget):
    """
    Workspace details microcomponent displaying environmental badges,
    compatibility parameters, play actions, and hosting the diagnostic card.
    """

    launch_requested = Signal(str, str)  # name, view_mode
    rename_requested = Signal(str)  # old_prefix_name
    auto_inject_requested = Signal(str, str)  # prefix_name, recipe_id
    explore_prefix_requested = Signal(str)  # prefix_name

    def __init__(self, active_gpu: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.active_gpu = active_gpu
        self.current_name = ""
        self.current_view = "games"
        self.current_recipe_id = "default_gaming"
        self.current_prefix = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 1. Header Card
        self.header_card = QFrame()
        self.header_card.setObjectName("CardFrame")
        h_layout = QVBoxLayout(self.header_card)

        self.lbl_game_title = QLabel("Ningún juego seleccionado")
        self.lbl_game_title.setObjectName("HeaderTitle")
        h_layout.addWidget(self.lbl_game_title)

        self.lbl_recipe_badge = QLabel("Receta: Ninguna")
        self.lbl_recipe_badge.setObjectName("Badge")
        self.lbl_recipe_badge.setAlignment(Qt.AlignLeft)
        h_layout.addWidget(self.lbl_recipe_badge)

        self.lbl_gpu_info = QLabel(f"Hardware: GPU {self.active_gpu.upper()}")
        self.lbl_gpu_info.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        h_layout.addWidget(self.lbl_gpu_info)

        self.lbl_env_status = QLabel("Estado: Ningún juego seleccionado")
        self.lbl_env_status.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #a1a1aa; padding: 2px 0px;"
        )
        h_layout.addWidget(self.lbl_env_status)

        self.btn_auto_inject = QPushButton("⚡ Instalar dependencias de receta")
        self.btn_auto_inject.setStyleSheet(
            "background-color: #202024; color: #ffb300; border: 1px solid #ffb300; font-weight: bold; padding: 6px;"
        )
        self.btn_auto_inject.clicked.connect(self._on_auto_inject_clicked)
        self.btn_auto_inject.hide()
        h_layout.addWidget(self.btn_auto_inject)

        # Primary Action / Play layout
        play_btn_layout = QHBoxLayout()
        play_btn_layout.setSpacing(6)

        self.btn_play = QPushButton("🔥 ¡AL ABORDAJE! (Lanzar)")
        self.btn_play.setObjectName("PlayButton")
        self.btn_play.clicked.connect(self._on_play_clicked)
        play_btn_layout.addWidget(self.btn_play, stretch=3)

        self.btn_secondary_action = QPushButton("✏️ Renombrar Entorno")
        self.btn_secondary_action.setStyleSheet(
            "background-color: #202024; color: #ffb300; border: 1px solid #ffb300; font-weight: bold; padding: 10px; font-size: 11px;"
        )
        self.btn_secondary_action.clicked.connect(self._on_secondary_clicked)
        self.btn_secondary_action.hide()
        play_btn_layout.addWidget(self.btn_secondary_action, stretch=1)

        h_layout.addLayout(play_btn_layout)
        layout.addWidget(self.header_card)

        # 2. Configuration Card
        self.config_card = QFrame()
        self.config_card.setObjectName("CardFrame")
        c_layout = QFormLayout(self.config_card)
        c_layout.setSpacing(8)

        self.combo_runners = QComboBox()
        c_layout.addRow("Runner Wine/Proton:", self.combo_runners)

        self.lbl_prefix_path = QLabel("Sin asignar")
        self.lbl_prefix_path.setStyleSheet("font-family: monospace; font-size: 11px;")
        c_layout.addRow("Carpeta WINEPREFIX:", self.lbl_prefix_path)

        self.lbl_exe_path = QLabel("Sin asignar")
        self.lbl_exe_path.setStyleSheet("font-family: monospace; font-size: 11px;")
        c_layout.addRow("Ejecutable .EXE:", self.lbl_exe_path)

        layout.addWidget(self.config_card)

        # 3. Encapsulated Diagnostic Log Card Microcomponent!
        self.log_card = DiagnosticLogCard()
        layout.addWidget(self.log_card)

    @Slot()
    def _on_play_clicked(self) -> None:
        self.launch_requested.emit(self.current_name, self.current_view)

    @Slot()
    def _on_secondary_clicked(self) -> None:
        if self.current_view == "envs":
            self.rename_requested.emit(self.current_name)

    @Slot()
    def _on_auto_inject_clicked(self) -> None:
        self.auto_inject_requested.emit(self.current_prefix, self.current_recipe_id)

    def populate_runners(self, runners: list[str]) -> None:
        self.combo_runners.blockSignals(True)
        self.combo_runners.clear()
        self.combo_runners.addItems(runners)
        self.combo_runners.addItem("Wine del Sistema (/usr/bin/wine)")
        self.combo_runners.blockSignals(False)

    def update_for_game(
        self,
        game_name: str,
        game_info: dict,
        recipe: dict,
        missing_verbs: list[str],
        prefixes_dir: Path,
    ) -> None:
        self.current_name = game_name
        self.current_view = "games"
        self.current_recipe_id = game_info.get("recipe_id", "default_gaming")
        self.current_prefix = game_info.get("prefix", "")

        self.lbl_game_title.setText(game_name)
        self.lbl_recipe_badge.setText(
            f"Receta: {recipe.get('display_name', self.current_recipe_id)}"
        )

        prefix_full = prefixes_dir / self.current_prefix
        self.lbl_prefix_path.setText(str(prefix_full))
        self.lbl_exe_path.setText(game_info.get("exe", "Sin asignar"))

        self.btn_play.setText("🔥 ¡AL ABORDAJE! (Lanzar)")
        self.btn_secondary_action.hide()

        idx = self.combo_runners.findText(game_info.get("runner", ""))
        if idx != -1:
            self.combo_runners.setCurrentIndex(idx)
        else:
            self.combo_runners.setCurrentIndex(0)

        if missing_verbs:
            self.lbl_env_status.setText(
                f"⚠️ Entorno incompleto (Falta: {', '.join(missing_verbs)})"
            )
            self.lbl_env_status.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #ffb300; padding: 2px 0px;"
            )
            self.btn_auto_inject.setText(
                f"⚡ Instalar dependencias de receta ({len(missing_verbs)} faltantes)"
            )
            self.btn_auto_inject.show()
        else:
            self.lbl_env_status.setText("✅ Entorno optimizado y listo")
            self.lbl_env_status.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #00e676; padding: 2px 0px;"
            )
            self.btn_auto_inject.hide()

    def update_for_env(
        self, env_name: str, recipe: dict, missing_verbs: list[str], prefixes_dir: Path
    ) -> None:
        self.current_name = env_name
        self.current_view = "envs"
        self.current_recipe_id = recipe.get("recipe_id", "default_gaming")
        self.current_prefix = env_name

        self.lbl_game_title.setText(f"Contenedor: {env_name}")
        self.lbl_recipe_badge.setText(
            f"Receta Vinculada: {recipe.get('display_name', 'Ninguna')}"
        )

        prefix_full = prefixes_dir / env_name
        self.lbl_prefix_path.setText(str(prefix_full))
        self.lbl_exe_path.setText("Varios (Contenedor de Sistema)")

        self.btn_play.setText("📂 ABRIR CARPETA DRIVE_C")
        self.btn_secondary_action.show()
        self.btn_secondary_action.setText("✏️ Renombrar Entorno")

        if missing_verbs:
            self.lbl_env_status.setText(
                f"⚠️ Contenedor incompleto (Falta: {', '.join(missing_verbs)})"
            )
            self.lbl_env_status.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #ffb300; padding: 4px 0px;"
            )
            self.btn_auto_inject.setText(
                f"⚡ Completar Entorno ({len(missing_verbs)} faltantes)"
            )
            self.btn_auto_inject.show()
        else:
            self.lbl_env_status.setText("✅ Contenedor optimizado y listo")
            self.lbl_env_status.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #00e676; padding: 4px 0px;"
            )
            self.btn_auto_inject.hide()
