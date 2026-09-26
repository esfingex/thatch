# views/settings_dialog.py
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFileDialog,
    QMessageBox,
    QWidget,
)
from PySide6.QtCore import Slot

from database import ThatchDB

from i18n import _


class SettingsDialog(QDialog):
    """
    Dedicated dialogue to modify global paths, winetricks directories,
    and general execution performance behaviors.
    """

    def __init__(self, db: ThatchDB, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(_("settings_window_title"))
        self.resize(500, 320)

        layout = QFormLayout(self)
        layout.setSpacing(12)

        # 1. Prefixes Dir
        pref_lay = QHBoxLayout()
        self.lbl_pref = QLabel(str(self.db.get_prefixes_dir()))
        self.lbl_pref.setStyleSheet("font-family: monospace; font-size: 11px;")
        btn_pref = QPushButton(_("btn_browse"))
        btn_pref.clicked.connect(self._browse_pref)
        pref_lay.addWidget(self.lbl_pref, stretch=3)
        pref_lay.addWidget(btn_pref, stretch=1)
        layout.addRow(_("lbl_chests_path"), pref_lay)

        # 2. Runners Dir
        run_lay = QHBoxLayout()
        self.lbl_run = QLabel(str(self.db.get_runners_dir()))
        self.lbl_run.setStyleSheet("font-family: monospace; font-size: 11px;")
        btn_run = QPushButton(_("btn_browse"))
        btn_run.clicked.connect(self._browse_runners)
        run_lay.addWidget(self.lbl_run, stretch=3)
        run_lay.addWidget(btn_run, stretch=1)
        layout.addRow(_("settings_lbl_runners"), run_lay)

        # 3. Cache Dir
        cache_lay = QHBoxLayout()
        self.lbl_cache = QLabel(str(self.db.get_winetricks_cache_dir()))
        self.lbl_cache.setStyleSheet("font-family: monospace; font-size: 11px;")
        btn_cache = QPushButton(_("btn_browse"))
        btn_cache.clicked.connect(self._browse_cache)
        cache_lay.addWidget(self.lbl_cache, stretch=3)
        cache_lay.addWidget(btn_cache, stretch=1)
        layout.addRow(_("settings_lbl_cache"), cache_lay)

        # 4. Launch Mode
        self.combo_mode = QComboBox()
        self.combo_mode.addItem(_("launch_close"), "extreme")
        self.combo_mode.addItem(_("launch_minimize"), "stealth")
        self.combo_mode.addItem(_("launch_keep"), "keep")
        layout.addRow(_("settings_lbl_launch_mode"), self.combo_mode)

        current_mode = self.db.get_launch_mode()
        idx = self.combo_mode.findData(current_mode)
        if idx != -1:
            self.combo_mode.setCurrentIndex(idx)

        # Save Button
        btn_save = QPushButton(_("settings_btn_save"))
        btn_save.setStyleSheet(
            "background-color: #0d5a2d; color: #00e676; border: 1px solid #00e676;"
        )
        btn_save.clicked.connect(self._save_settings)
        layout.addRow(btn_save)

    @Slot()
    def _browse_pref(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, _("settings_browse_prefixes_title"), self.lbl_pref.text()
        )
        if path:
            self.lbl_pref.setText(path)

    @Slot()
    def _browse_runners(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, _("settings_browse_runners_title"), self.lbl_run.text()
        )
        if path:
            self.lbl_run.setText(path)

    @Slot()
    def _browse_cache(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, _("settings_browse_cache_title"), self.lbl_cache.text()
        )
        if path:
            self.lbl_cache.setText(path)

    @Slot()
    def _save_settings(self) -> None:
        self.db.data["paths"]["prefixes_dir"] = self.lbl_pref.text()
        self.db.data["paths"]["runners_dir"] = self.lbl_run.text()
        self.db.data["paths"]["winetricks_cache"] = self.lbl_cache.text()
        self.db.data["preferences"]["launch_mode"] = self.combo_mode.currentData()
        self.db.save()
        QMessageBox.information(
            self,
            _("settings_saved_title"),
            _("settings_saved_msg"),
        )
        self.accept()
