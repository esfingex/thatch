import json
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QMessageBox,
    QComboBox,
)
from PySide6.QtCore import Qt


class RecipesView(QWidget):
    """
    Visual editor for JSON game recipes (Maps).
    """

    def __init__(self, recipes_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.recipes_dir = recipes_dir
        self.current_recipe_id = None
        self.recipes_cache = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

        # Header
        header = QVBoxLayout()
        header.setSpacing(4)
        lbl_title = QLabel("Editor de Mapas")
        lbl_title.setObjectName("ViewTitle")
        lbl_subtitle = QLabel(
            "Crea y edita mapas del tesoro (configuraciones JSON) para tus contenedores."
        )
        lbl_subtitle.setStyleSheet("color: #71717a; font-size: 13px;")
        header.addWidget(lbl_title)
        header.addWidget(lbl_subtitle)
        main_layout.addLayout(header)

        # Content Layout
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        main_layout.addLayout(content_layout, stretch=1)

        # Left Panel (List)
        left_widget = QWidget()
        left_widget.setFixedWidth(260)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        self.list_recipes = QListWidget()
        self.list_recipes.itemSelectionChanged.connect(self._on_recipe_selected)
        left_layout.addWidget(self.list_recipes)

        btn_new = QPushButton("+ Nuevo Mapa")
        btn_new.setObjectName("BlueBtn")
        btn_new.clicked.connect(self._on_new_recipe)
        left_layout.addWidget(btn_new)

        content_layout.addWidget(left_widget)

        # Right Panel (Editor Form)
        self.right_widget = QWidget()
        self.right_widget.setObjectName("DetailCard")
        right_layout = QVBoxLayout(self.right_widget)
        right_layout.setSpacing(12)

        lbl_id = QLabel("ID del Mapa (sin .json):")
        self.txt_id = QLineEdit()
        right_layout.addWidget(lbl_id)
        right_layout.addWidget(self.txt_id)

        lbl_name = QLabel("Nombre a Mostrar:")
        self.txt_name = QLineEdit()
        right_layout.addWidget(lbl_name)
        right_layout.addWidget(self.txt_name)

        lbl_verbs = QLabel("Cargamento / Dependencias (ej: dxvk, vkd3d):")
        self.txt_verbs = QLineEdit()
        right_layout.addWidget(lbl_verbs)
        right_layout.addWidget(self.txt_verbs)

        lbl_runner = QLabel("Motor Wine (ej: wine-cachyos):")
        self.cmb_runner = QComboBox()
        self.cmb_runner.setEditable(True)
        if parent and hasattr(parent, "_get_runners_list"):
            runners = ["wine-cachyos", "wine"] + parent._get_runners_list()
            self.cmb_runner.addItems(runners)
        right_layout.addWidget(lbl_runner)
        right_layout.addWidget(self.cmb_runner)

        lbl_desc = QLabel("Descripción:")
        self.txt_desc = QTextEdit()
        self.txt_desc.setMaximumHeight(80)
        right_layout.addWidget(lbl_desc)
        right_layout.addWidget(self.txt_desc)

        lbl_env = QLabel("Variables de Entorno (Formato JSON):")
        self.txt_env = QTextEdit()
        self.txt_env.setObjectName("ConsoleLog")  # Monospace font
        right_layout.addWidget(lbl_env)
        right_layout.addWidget(self.txt_env)

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Guardar Mapa")
        btn_save.setObjectName("OrangeBtn")
        btn_save.clicked.connect(self._on_save_recipe)
        btn_layout.addWidget(btn_save)

        btn_delete = QPushButton("Eliminar Mapa")
        btn_delete.setObjectName("RedBtn")
        btn_delete.clicked.connect(self._on_delete_recipe)
        btn_layout.addWidget(btn_delete)

        right_layout.addLayout(btn_layout)

        self.right_widget.setEnabled(False)
        content_layout.addWidget(self.right_widget, stretch=1)

        self._load_recipes()

    def _load_recipes(self) -> None:
        self.list_recipes.clear()
        self.recipes_cache.clear()

        if not self.recipes_dir.exists():
            self.recipes_dir.mkdir(parents=True, exist_ok=True)

        for file in self.recipes_dir.glob("*.json"):
            recipe_id = file.stem
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.recipes_cache[recipe_id] = data
                self.list_recipes.addItem(recipe_id)
            except Exception as e:
                print(f"Error loading {file}: {e}")

    def _on_recipe_selected(self) -> None:
        selected = self.list_recipes.selectedItems()
        if not selected:
            self.right_widget.setEnabled(False)
            return

        recipe_id = selected[0].text()
        self.current_recipe_id = recipe_id
        data = self.recipes_cache.get(recipe_id, {})

        self.txt_id.setText(recipe_id)
        self.txt_id.setEnabled(False)  # Can't rename file easily here

        self.txt_name.setText(data.get("display_name", ""))
        self.txt_verbs.setText(", ".join(data.get("required_verbs", [])))
        self.cmb_runner.setCurrentText(data.get("recommended_runner", "wine-cachyos"))
        self.txt_desc.setPlainText(data.get("description", ""))

        env_data = data.get("performance_env", {})
        self.txt_env.setPlainText(json.dumps(env_data, indent=2))

        self.right_widget.setEnabled(True)

    def _on_new_recipe(self) -> None:
        self.list_recipes.clearSelection()
        self.current_recipe_id = None
        self.txt_id.setEnabled(True)
        self.txt_id.clear()
        self.txt_name.clear()
        self.txt_verbs.clear()
        self.cmb_runner.setCurrentText("wine-cachyos")
        self.txt_desc.clear()
        self.txt_env.setPlainText('{\n  "WINEESYNC": "1",\n  "WINEMFSYNC": "1"\n}')
        self.right_widget.setEnabled(True)
        self.txt_id.setFocus()

    def _on_save_recipe(self) -> None:
        recipe_id = self.txt_id.text().strip()
        if not recipe_id:
            QMessageBox.warning(self, "Error", "Debes especificar un ID para el mapa.")
            return

        verbs_raw = self.txt_verbs.text().split(",")
        verbs = [v.strip() for v in verbs_raw if v.strip()]

        try:
            env_json = json.loads(self.txt_env.toPlainText() or "{}")
        except json.JSONDecodeError:
            QMessageBox.critical(
                self,
                "Error de Formato",
                "Las variables de entorno deben estar en formato JSON válido.",
            )
            return

        data = {
            "display_name": self.txt_name.text().strip(),
            "required_verbs": verbs,
            "recommended_runner": self.cmb_runner.currentText().strip(),
            "description": self.txt_desc.toPlainText().strip(),
            "performance_env": env_json,
        }

        file_path = self.recipes_dir / f"{recipe_id}.json"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            QMessageBox.information(
                self, "Guardado", f"Mapa '{recipe_id}' guardado exitosamente."
            )
            self._load_recipes()

            # Re-select the saved item
            items = self.list_recipes.findItems(recipe_id, Qt.MatchExactly)
            if items:
                self.list_recipes.setCurrentItem(items[0])

        except Exception as e:
            QMessageBox.critical(
                self, "Error al guardar", f"No se pudo guardar el mapa:\n{e}"
            )

    def _on_delete_recipe(self) -> None:
        recipe_id = self.txt_id.text().strip()
        if not recipe_id:
            return

        reply = QMessageBox.question(
            self,
            "Confirmar Eliminación",
            f"¿Estás seguro de que quieres eliminar el mapa '{recipe_id}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            file_path = self.recipes_dir / f"{recipe_id}.json"
            try:
                if file_path.exists():
                    file_path.unlink()
                QMessageBox.information(
                    self, "Eliminado", "Mapa eliminado correctamente."
                )
                self.list_recipes.clearSelection()
                self._on_new_recipe()
                self._load_recipes()
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"No se pudo eliminar el mapa:\n{e}"
                )
