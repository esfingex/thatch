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

from i18n import _


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
        self.lbl_title = QLabel(_("recipes_title"))
        self.lbl_title.setObjectName("ViewTitle")
        self.lbl_subtitle = QLabel(_("recipes_subtitle"))
        self.lbl_subtitle.setStyleSheet("color: #71717a; font-size: 13px;")
        header.addWidget(self.lbl_title)
        header.addWidget(self.lbl_subtitle)
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

        self.btn_new = QPushButton(_("recipes_btn_new"))
        self.btn_new.setObjectName("BlueBtn")
        self.btn_new.clicked.connect(self._on_new_recipe)
        left_layout.addWidget(self.btn_new)

        content_layout.addWidget(left_widget)

        # Right Panel (Editor Form)
        self.right_widget = QWidget()
        self.right_widget.setObjectName("DetailCard")
        right_layout = QVBoxLayout(self.right_widget)
        right_layout.setSpacing(12)

        self.lbl_id = QLabel(_("recipes_lbl_id"))
        self.txt_id = QLineEdit()
        right_layout.addWidget(self.lbl_id)
        right_layout.addWidget(self.txt_id)

        self.lbl_name = QLabel(_("recipes_lbl_name"))
        self.txt_name = QLineEdit()
        right_layout.addWidget(self.lbl_name)
        right_layout.addWidget(self.txt_name)

        self.lbl_verbs = QLabel(_("recipes_lbl_verbs"))
        self.txt_verbs = QLineEdit()
        right_layout.addWidget(self.lbl_verbs)
        right_layout.addWidget(self.txt_verbs)

        self.lbl_runner = QLabel(_("recipes_lbl_runner"))
        self.cmb_runner = QComboBox()
        self.cmb_runner.setEditable(True)
        if parent and hasattr(parent, "_get_runners_list"):
            runners = ["wine-cachyos", "wine"] + parent._get_runners_list()
            self.cmb_runner.addItems(runners)
        right_layout.addWidget(self.lbl_runner)
        right_layout.addWidget(self.cmb_runner)

        self.lbl_desc = QLabel(_("recipes_lbl_desc"))
        self.txt_desc = QTextEdit()
        self.txt_desc.setMaximumHeight(80)
        right_layout.addWidget(self.lbl_desc)
        right_layout.addWidget(self.txt_desc)

        self.lbl_env = QLabel(_("recipes_lbl_env"))
        self.txt_env = QTextEdit()
        self.txt_env.setObjectName("ConsoleLog")  # Monospace font
        right_layout.addWidget(self.lbl_env)
        right_layout.addWidget(self.txt_env)

        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton(_("recipes_btn_save"))
        self.btn_save.setObjectName("OrangeBtn")
        self.btn_save.clicked.connect(self._on_save_recipe)
        btn_layout.addWidget(self.btn_save)

        self.btn_delete = QPushButton(_("recipes_btn_delete"))
        self.btn_delete.setObjectName("RedBtn")
        self.btn_delete.clicked.connect(self._on_delete_recipe)
        btn_layout.addWidget(self.btn_delete)

        right_layout.addLayout(btn_layout)

        self.right_widget.setEnabled(False)
        content_layout.addWidget(self.right_widget, stretch=1)

        self._load_recipes()

    def retranslate(self) -> None:
        """Refreshes static labels and buttons with the active language."""
        self.lbl_title.setText(_("recipes_title"))
        self.lbl_subtitle.setText(_("recipes_subtitle"))
        self.btn_new.setText(_("recipes_btn_new"))
        self.lbl_id.setText(_("recipes_lbl_id"))
        self.lbl_name.setText(_("recipes_lbl_name"))
        self.lbl_verbs.setText(_("recipes_lbl_verbs"))
        self.lbl_runner.setText(_("recipes_lbl_runner"))
        self.lbl_desc.setText(_("recipes_lbl_desc"))
        self.lbl_env.setText(_("recipes_lbl_env"))
        self.btn_save.setText(_("recipes_btn_save"))
        self.btn_delete.setText(_("recipes_btn_delete"))

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
            QMessageBox.warning(self, _("recipes_error_title"), _("recipes_err_no_id"))
            return

        verbs_raw = self.txt_verbs.text().split(",")
        verbs = [v.strip() for v in verbs_raw if v.strip()]

        try:
            env_json = json.loads(self.txt_env.toPlainText() or "{}")
        except json.JSONDecodeError:
            QMessageBox.critical(
                self,
                _("recipes_err_format_title"),
                _("recipes_err_format_msg"),
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
                self,
                _("recipes_saved_title"),
                _("recipes_saved_msg", name=recipe_id),
            )
            self._load_recipes()

            # Re-select the saved item
            items = self.list_recipes.findItems(recipe_id, Qt.MatchExactly)
            if items:
                self.list_recipes.setCurrentItem(items[0])

        except Exception as e:
            QMessageBox.critical(
                self, _("recipes_err_save_title"), _("recipes_save_failed_msg", error=e)
            )

    def _on_delete_recipe(self) -> None:
        recipe_id = self.txt_id.text().strip()
        if not recipe_id:
            return

        reply = QMessageBox.question(
            self,
            _("recipes_confirm_delete_title"),
            _("recipes_confirm_delete_msg", name=recipe_id),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            file_path = self.recipes_dir / f"{recipe_id}.json"
            try:
                if file_path.exists():
                    file_path.unlink()
                QMessageBox.information(self, _("recipes_deleted_title"), _("recipes_deleted_msg"))
                self.list_recipes.clearSelection()
                self._on_new_recipe()
                self._load_recipes()
            except Exception as e:
                QMessageBox.critical(
                    self, _("recipes_error_title"), _("recipes_delete_failed_msg", error=e)
                )
