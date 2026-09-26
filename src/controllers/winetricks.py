"""Winetricks catalog and dependency-injection machinery, extracted from main.py."""

from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QMessageBox

import core
from i18n import _


class WinetricksController(QObject):
    """Owns the winetricks catalog cache and the dependency-injection QProcess queue.

    The launcher keeps ownership of the shared ``process`` and ``console_dialog``
    state because the chest-creation flow (ChestsController) and the injection
    queue interleave on the same QProcess.
    """

    _catalog_ready = Signal(int)
    _catalog_failed = Signal()
    _catalog_error = Signal(str)

    def __init__(self, launcher) -> None:
        super().__init__(launcher)
        self.launcher = launcher
        self._winetricks_catalog: list[dict] | None = None  # lazy cache
        self.winetricks_queue: list[str] = []
        self.winetricks_queue_prefix = ""

        # Connect background catalog signals
        self._catalog_ready.connect(self._on_catalog_ready)
        self._catalog_failed.connect(self._on_catalog_failed)
        self._catalog_error.connect(self._on_catalog_error)

    # ─── WINETRICKS CATALOG SERVICES ──────────────────────────────────────────

    def load_winetricks_catalog(self) -> list[dict]:
        if self._winetricks_catalog is not None:
            return self._winetricks_catalog

        try:
            cached = self.launcher.db.get_winetricks_catalog()
            if cached:
                self._winetricks_catalog = cached
                return cached
        except Exception as e:
            print(f"[WinetricksCatalog] Failed to read SQLite cache: {e}")

        self._winetricks_catalog = []
        self._trigger_winetricks_catalog_refresh(silent=True)
        return self._winetricks_catalog

    def _trigger_winetricks_catalog_refresh(self, silent: bool = True) -> None:
        core.scan_winetricks_catalog_bg(
            self.launcher.db,
            self._catalog_ready,
            self._catalog_failed,
            self._catalog_error,
            silent=silent,
        )

    @Slot(int)
    def _on_catalog_ready(self, count: int) -> None:
        self.launcher.toast.show_message(_("toast_catalog_updated", count=count))
        self.launcher.refresh_data()

    @Slot()
    def _on_catalog_failed(self) -> None:
        self.launcher.toast.show_message(_("toast_catalog_failed"))

    @Slot(str)
    def _on_catalog_error(self, message: str) -> None:
        self.launcher.toast.show_message(message)

    @Slot()
    def _on_update_catalog_requested(self) -> None:
        self.launcher.toast.show_message(_("toast_catalog_updating"))
        self._trigger_winetricks_catalog_refresh(silent=False)

    def get_installed_verbs(self, prefix_name: str) -> list[str]:
        prefix_path = self.launcher.db.get_prefixes_dir() / prefix_name
        log_path = prefix_path / "winetricks.log"
        installed = []
        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        tokens = line.split()
                        if len(tokens) >= 2:
                            installed.append(tokens[1])
            except Exception as e:
                print(f"Error reading winetricks.log: {e}")
        return installed

    def register_installed_verb(self, prefix_name: str, verb: str) -> None:
        prefix_path = self.launcher.db.get_prefixes_dir() / prefix_name
        log_path = prefix_path / "winetricks.log"
        prefix_path.mkdir(parents=True, exist_ok=True)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"w_workaround {verb}\n")
        except Exception as e:
            print(f"Error writing winetricks.log: {e}")

    # ─── WINETRICKS DEPENDENCY INJECTIONS ──────────────────────────────────────

    @Slot(str, str)
    def _on_chest_install_dependency(self, prefix_name: str, verb: str) -> None:
        self._queue_winetricks_injections(prefix_name, [verb])

    @Slot(str, str)
    def _on_chest_remove_dependency(self, prefix_name: str, verb: str) -> None:
        prefix_path = self.launcher.db.get_prefixes_dir() / prefix_name
        log_path = prefix_path / "winetricks.log"
        if log_path.exists():
            try:
                lines = []
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                with open(log_path, "w", encoding="utf-8") as f:
                    for line in lines:
                        if not (verb in line and line.strip().startswith("w_workaround")):
                            f.write(line)
                self.launcher.toast.show_message(_("main_toast_verb_removed", verb=verb))
                self.launcher.refresh_data()
            except Exception as e:
                QMessageBox.critical(
                    self.launcher, _("main_error_title"), _("main_error_remove_verb_log", error=e)
                )

    def _queue_winetricks_injections(self, prefix_name: str, verbs: list[str]) -> None:
        self.winetricks_queue.extend(verbs)
        self.winetricks_queue_prefix = prefix_name

        if not (self.launcher.process and self.launcher.process.state() == QProcess.Running):
            self._process_next_winetricks_queue()

    def _process_next_winetricks_queue(self) -> None:
        if not self.winetricks_queue:
            return

        verb = self.winetricks_queue.pop(0)
        prefix_name = self.winetricks_queue_prefix
        recipe_id = self.launcher.chests_ctrl._get_chest_recipe_id(prefix_name)

        env, runner_path = self.launcher.get_wine_env(prefix_name, recipe_id)
        wine_exe = self.launcher._get_wine_cmd(runner_path)

        self.current_prefix = prefix_name
        self.current_verb = verb

        self.launcher.console_dialog = core.WinetricksConsoleDialog(
            verb, prefix_name, self.launcher
        )

        self.launcher.process = QProcess()
        self.launcher.process.readyReadStandardOutput.connect(self._on_winetricks_stdout)
        self.launcher.process.readyReadStandardError.connect(self._on_winetricks_stderr)

        def _finish_handler(exit_code: int, exit_status: QProcess.ExitStatus):
            self._on_winetricks_finished(exit_code, prefix_name, verb)

        self.launcher.process.finished.connect(_finish_handler)
        self.launcher.process.errorOccurred.connect(self._on_winetricks_error)

        q_env = QProcessEnvironment.systemEnvironment()
        for k, v in env.items():
            q_env.insert(k, v)

        q_env.insert("DISPLAY", "")
        q_env.insert("WINEHEADLESS", "1")
        q_env.insert("WINEESYNC", "0")
        q_env.insert("WINEFSYNC", "0")
        q_env.insert("WINEMFSYNC", "0")
        q_env.insert("WINEDEBUG", "-all")

        if "WINEDLLOVERRIDES" in env:
            q_env.insert("WINEDLLOVERRIDES", env["WINEDLLOVERRIDES"] + ";mscoree,mshtml=d")
        else:
            q_env.insert("WINEDLLOVERRIDES", "mscoree,mshtml=d")

        recipe_obj = self.launcher.recipes.get(recipe_id, {})
        recipe_perf = recipe_obj.get("performance_env", {})
        if recipe_perf.get("WINEARCH") == "win64" or recipe_perf.get("WINEARCH64"):
            q_env.insert("WINEARCH", "win64")

        self.launcher.process.setProcessEnvironment(q_env)

        import shutil

        if not shutil.which("winetricks"):
            QMessageBox.critical(
                self.launcher,
                _("main_error_title"),
                _("main_error_no_winetricks"),
            )
            return

        wineserver_bin = (
            Path(wine_exe).parent / "wineserver"
            if Path(wine_exe).parent.name in ("bin", "files")
            else "wineserver"
        )
        cmd_str = f'winetricks -q {verb}; "{wine_exe}" wineboot -u; "{wineserver_bin}" -w'

        self.launcher.process.start("bash", ["-c", cmd_str])
        self.launcher.console_dialog.show()

    def _on_winetricks_stdout(self) -> None:
        if self.launcher.process and self.launcher.console_dialog:
            data = (
                self.launcher.process.readAllStandardOutput()
                .data()
                .decode("utf-8", errors="ignore")
            )
            self.launcher.console_dialog.console.append(data)

    def _on_winetricks_stderr(self) -> None:
        if self.launcher.process and self.launcher.console_dialog:
            data = (
                self.launcher.process.readAllStandardError().data().decode("utf-8", errors="ignore")
            )
            self.launcher.console_dialog.console.append(data)

    def _on_winetricks_error(self, error: QProcess.ProcessError) -> None:
        print(f"[Winetricks Error] QProcess failed: {error}")
        if self.launcher.console_dialog:
            self.launcher.console_dialog.console.append(_("main_wt_error_console", error=error))
            self.launcher.console_dialog.btn_close.setEnabled(True)

    def _on_winetricks_finished(self, exit_code: int, prefix_name: str, verb: str) -> None:
        if self.launcher.console_dialog:
            self.launcher.console_dialog.console.append(
                _("main_wt_finished_console", exit_code=exit_code)
            )
            self.launcher.console_dialog.btn_close.setEnabled(True)

        if exit_code == 0:
            self.register_installed_verb(prefix_name, verb)
            self.launcher.toast.show_message(_("main_toast_verb_injected", verb=verb))
            self.launcher.refresh_data()
        else:
            QMessageBox.warning(
                self.launcher,
                _("main_injection_failed_title"),
                _("main_injection_failed_msg", exit_code=exit_code, verb=verb),
            )

        if self.winetricks_queue:
            QTimer.singleShot(300, self._process_next_winetricks_queue)
