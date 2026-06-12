from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QFrame,
    QScrollArea,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QGridLayout,
)
from PySide6.QtCore import Slot, Qt, Signal
import math
import shutil
from database import ThatchDB
from i18n import _, ACTIVE_LANG


class PreferencesView(QWidget):
    """
    Unified Application Preferences view. Merges default configurations,
    folder paths, and the Winetricks cache cleaner into a single unified menu.
    """

    toast_requested = Signal(str)
    update_catalog_requested = Signal()

    def __init__(
        self, db: ThatchDB, runners: list[str], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.runners = runners

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # 1. Header Title
        self.lbl_title = QLabel(_("pref_title"))
        self.lbl_title.setObjectName("ViewTitle")
        layout.addWidget(self.lbl_title)

        # 2. Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: transparent; }"
        )

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(16)

        # COMBINED CARD: Application Settings & Paths
        card_prefs = QFrame()
        card_prefs.setObjectName("PrefCard")
        prefs_layout = QVBoxLayout(card_prefs)
        prefs_layout.setSpacing(16)

        self.lbl_card_title = QLabel(_("pref_card_title"))
        self.lbl_card_title.setObjectName("CardTitle")
        prefs_layout.addWidget(self.lbl_card_title)

        # Form grid combining defaults and paths
        grid = QGridLayout()
        grid.setSpacing(14)

        # Row 0: Default Runner
        self.lbl_runner = QLabel(_("lbl_default_runner"))
        self.lbl_runner.setObjectName("CardLabel")
        self.combo_runner = QComboBox()
        self._populate_runners_combo()
        self.combo_runner.currentTextChanged.connect(self._save_default_runner)
        grid.addWidget(self.lbl_runner, 0, 0)
        grid.addWidget(
            self.combo_runner, 0, 1, 1, 2
        )  # Span columns to match browse buttons

        # Row 1: Launch Action
        self.lbl_launch = QLabel(_("lbl_launch_action"))
        self.lbl_launch.setObjectName("CardLabel")
        self.combo_launch = QComboBox()
        self.combo_launch.addItem(_("launch_close"), "extreme")
        self.combo_launch.addItem(_("launch_minimize"), "stealth")
        self.combo_launch.addItem(_("launch_keep"), "keep")
        self.combo_launch.currentTextChanged.connect(self._save_launch_mode)
        grid.addWidget(self.lbl_launch, 1, 0)
        grid.addWidget(self.combo_launch, 1, 1, 1, 2)

        # Row 2: Default Terminal
        self.lbl_term = QLabel(_("lbl_default_terminal"))
        self.lbl_term.setObjectName("CardLabel")
        self.combo_term = QComboBox()
        self.installed_terminals = self._scan_installed_terminals()
        self.combo_term.addItems(self.installed_terminals)
        self.combo_term.currentTextChanged.connect(self._save_default_terminal)
        grid.addWidget(self.lbl_term, 2, 0)
        grid.addWidget(self.combo_term, 2, 1, 1, 2)

        # Row 3: Chests Path
        self.lbl_path_pref = QLabel(_("lbl_chests_path"))
        self.lbl_path_pref.setObjectName("CardLabel")
        self.txt_path_pref = QLineEdit(str(self.db.get_prefixes_dir()))
        self.txt_path_pref.setReadOnly(True)
        self.btn_path_pref = QPushButton(_("btn_browse"))
        self.btn_path_pref.setCursor(Qt.PointingHandCursor)
        self.btn_path_pref.clicked.connect(self._browse_prefixes)
        grid.addWidget(self.lbl_path_pref, 3, 0)
        grid.addWidget(self.txt_path_pref, 3, 1)
        grid.addWidget(self.btn_path_pref, 3, 2)

        # Row 4: Runners Path
        self.lbl_path_run = QLabel(_("lbl_runners_path"))
        self.lbl_path_run.setObjectName("CardLabel")
        self.txt_path_run = QLineEdit(str(self.db.get_runners_dir()))
        self.txt_path_run.setReadOnly(True)
        self.btn_path_run = QPushButton(_("btn_browse"))
        self.btn_path_run.setCursor(Qt.PointingHandCursor)
        self.btn_path_run.clicked.connect(self._browse_runners)
        grid.addWidget(self.lbl_path_run, 4, 0)
        grid.addWidget(self.txt_path_run, 4, 1)
        grid.addWidget(self.btn_path_run, 4, 2)

        # Row 5: Winetricks Cache Path
        self.lbl_path_cache = QLabel(_("lbl_winetricks_cache"))
        self.lbl_path_cache.setObjectName("CardLabel")
        self.txt_path_cache = QLineEdit(str(self.db.get_winetricks_cache_dir()))
        self.txt_path_cache.setReadOnly(True)
        self.btn_path_cache = QPushButton(_("btn_browse"))
        self.btn_path_cache.setCursor(Qt.PointingHandCursor)
        self.btn_path_cache.clicked.connect(self._browse_cache)
        grid.addWidget(self.lbl_path_cache, 5, 0)
        grid.addWidget(self.txt_path_cache, 5, 1)
        grid.addWidget(self.btn_path_cache, 5, 2)

        # Row 6: App Language selector
        self.lbl_lang = QLabel(_("lbl_app_language"))
        self.lbl_lang.setObjectName("CardLabel")
        self.combo_language = QComboBox()
        self.combo_language.addItem(_("opt_english"), "en")
        self.combo_language.addItem(_("opt_spanish"), "es")
        grid.addWidget(self.lbl_lang, 6, 0)
        grid.addWidget(self.combo_language, 6, 1, 1, 2)

        prefs_layout.addLayout(grid)

        # Winetricks Cache stats & cleanup row
        self.cache_mgr_frame = QFrame()
        self.cache_mgr_frame.setStyleSheet(
            "background-color: #121214; border: 1px solid #2d2d34; border-radius: 6px; padding: 12px;"
        )
        cache_layout = QHBoxLayout(self.cache_mgr_frame)
        cache_layout.setContentsMargins(12, 8, 12, 8)

        self.lbl_cache_title = QLabel(_("lbl_winetricks_cache_size"))
        self.lbl_cache_title.setStyleSheet(
            "color: #ffffff; font-size: 12px; font-weight: bold;"
        )
        self.lbl_cache_size = QLabel(_("lbl_scan_size"))
        self.lbl_cache_size.setStyleSheet("color: #8e8e93; font-size: 12px;")

        self.btn_update_catalog = QPushButton(_("btn_update_catalog"))
        self.btn_update_catalog.setCursor(Qt.PointingHandCursor)
        self.btn_update_catalog.setStyleSheet(
            "padding: 4px 10px; font-size: 11px; color: #ffffff; background-color: #2563eb; border: none; border-radius: 4px; margin-right: 8px;"
        )
        self.btn_update_catalog.clicked.connect(self.update_catalog_requested.emit)

        self.btn_clear_cache = QPushButton(_("btn_clear_cache"))
        self.btn_clear_cache.setObjectName("RedBtnText")
        self.btn_clear_cache.setCursor(Qt.PointingHandCursor)
        self.btn_clear_cache.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        self.btn_clear_cache.clicked.connect(self._clear_winetricks_cache)

        cache_layout.addWidget(self.lbl_cache_title)
        cache_layout.addWidget(self.lbl_cache_size)
        cache_layout.addStretch(1)
        cache_layout.addWidget(self.btn_update_catalog)
        cache_layout.addWidget(self.btn_clear_cache)
        prefs_layout.addWidget(self.cache_mgr_frame)

        # Static System Details
        self.lbl_specs_title = QLabel(_("lbl_system_details"))
        self.lbl_specs_title.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: bold; margin-top: 10px;"
        )
        prefs_layout.addWidget(self.lbl_specs_title)

        self.lbl_specs = QLabel(_("win_specs"))
        self.lbl_specs.setStyleSheet(
            "color: #71717a; font-size: 12px; line-height: 18px;"
        )
        prefs_layout.addWidget(self.lbl_specs)

        scroll_layout.addWidget(card_prefs)
        scroll_layout.addStretch(1)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        # Initial loads
        self._load_config_vals()
        self._refresh_cache_size()

    def retranslate(self) -> None:
        """Dynamically retranslates all label and button text in the Preferences view."""
        self.lbl_title.setText(_("pref_title"))
        self.lbl_card_title.setText(_("pref_card_title"))
        self.lbl_runner.setText(_("lbl_default_runner"))
        self.lbl_launch.setText(_("lbl_launch_action"))
        self.lbl_term.setText(_("lbl_default_terminal"))
        self.lbl_path_pref.setText(_("lbl_chests_path"))
        self.btn_path_pref.setText(_("btn_browse"))
        self.lbl_path_run.setText(_("lbl_runners_path"))
        self.btn_path_run.setText(_("btn_browse"))
        self.lbl_path_cache.setText(_("lbl_winetricks_cache"))
        self.btn_path_cache.setText(_("btn_browse"))
        self.lbl_cache_title.setText(_("lbl_winetricks_cache_size"))
        self.btn_update_catalog.setText(_("btn_update_catalog"))
        self.btn_clear_cache.setText(_("btn_clear_cache"))
        self.lbl_specs_title.setText(_("lbl_system_details"))
        self.lbl_specs.setText(_("win_specs"))
        self.lbl_lang.setText(_("lbl_app_language"))

        # 1. combo_launch
        launch_mode = self.combo_launch.currentData()
        self.combo_launch.blockSignals(True)
        self.combo_launch.clear()
        self.combo_launch.addItem(_("launch_close"), "extreme")
        self.combo_launch.addItem(_("launch_minimize"), "stealth")
        self.combo_launch.addItem(_("launch_keep"), "keep")
        idx = self.combo_launch.findData(launch_mode)
        if idx != -1:
            self.combo_launch.setCurrentIndex(idx)
        self.combo_launch.blockSignals(False)

        # 2. combo_runner
        runner_text = self.combo_runner.currentText()
        self.combo_runner.blockSignals(True)
        self._populate_runners_combo()
        if runner_text in [
            "System Wine (/usr/bin/wine)",
            "Wine del Sistema (/usr/bin/wine)",
        ]:
            idx_run = self.combo_runner.findText(_("win_system_wine"))
        else:
            idx_run = self.combo_runner.findText(runner_text)
        if idx_run != -1:
            self.combo_runner.setCurrentIndex(idx_run)
        self.combo_runner.blockSignals(False)

        # 3. combo_language
        lang_mode = self.combo_language.currentData()
        self.combo_language.blockSignals(True)
        self.combo_language.clear()
        self.combo_language.addItem(_("opt_english"), "en")
        self.combo_language.addItem(_("opt_spanish"), "es")
        idx_lang = self.combo_language.findData(lang_mode)
        if idx_lang != -1:
            self.combo_language.setCurrentIndex(idx_lang)
        self.combo_language.blockSignals(False)

        # 4. Refresh cache size text if it says "Scanning size..."
        if self.lbl_cache_size.text() in ["Scanning size...", "Escaneando tamaño..."]:
            self.lbl_cache_size.setText(_("lbl_scan_size"))

    def _populate_runners_combo(self) -> None:
        self.combo_runner.clear()
        if self.runners:
            self.combo_runner.addItems(self.runners)
        self.combo_runner.addItem(_("win_system_wine"))

    def _load_config_vals(self) -> None:
        """Prefills UI components with active db values."""
        # Launch action mode
        launch_mode = self.db.get_launch_mode()
        idx = self.combo_launch.findData(launch_mode)
        if idx != -1:
            self.combo_launch.setCurrentIndex(idx)

        # Default runner
        default_runner = self.db.data["global_config"].get("default_runner", "")
        if default_runner:
            # Fallback handling for "Wine del Sistema" matching win_system_wine key translation
            if default_runner in [
                "Wine del Sistema (/usr/bin/wine)",
                "System Wine (/usr/bin/wine)",
            ]:
                idx_run = self.combo_runner.findText(_("win_system_wine"))
            else:
                idx_run = self.combo_runner.findText(default_runner)
            if idx_run != -1:
                self.combo_runner.setCurrentIndex(idx_run)

        # Default terminal
        default_term = self.db.data["global_config"].get("default_terminal", "")
        if default_term:
            idx_term = self.combo_term.findText(default_term)
            if idx_term != -1:
                self.combo_term.setCurrentIndex(idx_term)

        # App Language
        app_lang = self.db.data["global_config"].get("app_language", ACTIVE_LANG)
        idx_lang = self.combo_language.findData(app_lang)
        if idx_lang != -1:
            self.combo_language.blockSignals(True)
            self.combo_language.setCurrentIndex(idx_lang)
            self.combo_language.blockSignals(False)

    def _scan_installed_terminals(self) -> list[str]:
        import shutil

        terminals = [
            "gnome-terminal",
            "konsole",
            "alacritty",
            "kitty",
            "xfce4-terminal",
            "xterm",
            "tilix",
        ]
        installed = []
        for term in terminals:
            if shutil.which(term):
                installed.append(term)
        if not installed:
            installed.append("xterm")
        return installed

    @Slot()
    def _save_default_terminal(self) -> None:
        self.db.data["global_config"]["default_terminal"] = (
            self.combo_term.currentText()
        )
        self.db.save()

    def update_runners_list(self, runners: list[str]) -> None:
        """Externally updates the list of installed wine runners."""
        self.runners = runners
        self._populate_runners_combo()
        self._load_config_vals()

    def _refresh_cache_size(self) -> None:
        """Calculates disk space taken up by winetricks cache folder."""
        cache_path = self.db.get_winetricks_cache_dir()
        if not cache_path.exists():
            self.lbl_cache_size.setText("0 B")
            return

        try:
            total_bytes = sum(
                f.stat().st_size for f in cache_path.glob("**/*") if f.is_file()
            )
            if total_bytes == 0:
                self.lbl_cache_size.setText("0 B")
            else:
                size_names = ("B", "KB", "MB", "GB", "TB")
                i = int(math.floor(math.log(total_bytes, 1024)))
                p = math.pow(1024, i)
                s = round(total_bytes / p, 2)
                self.lbl_cache_size.setText(f"{s} {size_names[i]}")
        except Exception as e:
            self.lbl_cache_size.setText("Unknown size")
            print(f"Error calculating cache size: {e}")

    @Slot()
    def _clear_winetricks_cache(self) -> None:
        cache_path = self.db.get_winetricks_cache_dir()
        if not cache_path.exists() or not any(cache_path.iterdir()):
            title = "Cache Empty" if ACTIVE_LANG == "en" else "Caché Vacío"
            msg = (
                "Winetricks cache is already empty."
                if ACTIVE_LANG == "en"
                else "El caché de Winetricks ya está vacío."
            )
            QMessageBox.information(self, title, msg)
            return

        title = (
            "Clear Winetricks Cache"
            if ACTIVE_LANG == "en"
            else "Limpiar Caché de Winetricks"
        )
        msg = (
            f"Are you sure you want to delete all cached files in {cache_path}?\nThis will remove installers that need to be re-downloaded next time you inject dependencies."
            if ACTIVE_LANG == "en"
            else f"¿Seguro que deseas eliminar todos los archivos en caché en {cache_path}?\nEsto borrará instaladores que se deberán descargar de nuevo cuando inyectes dependencias."
        )
        confirm = QMessageBox.question(
            self, title, msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if confirm == QMessageBox.Yes:
            try:
                for item in cache_path.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                self._refresh_cache_size()
                self.toast_requested.emit(_("toast_cache_cleared"))
            except Exception as e:
                err_title = "Error"
                QMessageBox.critical(self, err_title, f"Failed to clear cache: {e}")

    @Slot()
    def _save_default_runner(self) -> None:
        self.db.data["global_config"]["default_runner"] = (
            self.combo_runner.currentText()
        )
        self.db.save()

    @Slot()
    def _save_launch_mode(self) -> None:
        mode = self.combo_launch.currentData()
        self.db.set_launch_mode(mode)

    @Slot()
    def _browse_prefixes(self) -> None:
        title = (
            "Select Chests Directory"
            if ACTIVE_LANG == "en"
            else "Seleccionar Carpeta de Contenedores"
        )
        path = QFileDialog.getExistingDirectory(self, title, self.txt_path_pref.text())
        if path:
            self.txt_path_pref.setText(path)
            self.db.set_prefixes_dir(path)
            self.toast_requested.emit(_("toast_prefix_updated"))

    @Slot()
    def _browse_runners(self) -> None:
        title = (
            "Select Wine Runners Directory"
            if ACTIVE_LANG == "en"
            else "Seleccionar Carpeta de Motores Wine"
        )
        path = QFileDialog.getExistingDirectory(self, title, self.txt_path_run.text())
        if path:
            self.txt_path_run.setText(path)
            self.db.set_runners_dir(path)
            self.toast_requested.emit(_("toast_runners_updated"))

    @Slot()
    def _browse_cache(self) -> None:
        title = (
            "Select Winetricks Cache Directory"
            if ACTIVE_LANG == "en"
            else "Seleccionar Carpeta de Caché Winetricks"
        )
        path = QFileDialog.getExistingDirectory(self, title, self.txt_path_cache.text())
        if path:
            self.txt_path_cache.setText(path)
            self.db.set_winetricks_cache_dir(path)
            self._refresh_cache_size()
            self.toast_requested.emit(_("toast_cache_updated"))
