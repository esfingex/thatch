"""Chest action handlers and the chest-creation flow, extracted from main.py."""

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QObject, QTimer, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMessageBox,
)

import core
from desktop_integration import update_system_context_menu
from i18n import _
from views import CreateChestWizard


class ChestsController(QObject):
    """Handles chest grid/details actions and the chest-creation wizard flow.

    Shared launcher state (``process``, ``console_dialog``) stays on
    ``ThatchLauncher`` because the wineboot creation flow and the winetricks
    injection queue interleave on the same QProcess.
    """

    def __init__(self, launcher) -> None:
        super().__init__(launcher)
        self.launcher = launcher

    # ─── CHESTS GRID VIEW ACTIONS ──────────────────────────────────────────────

    @Slot()
    def _on_create_chest_requested(self) -> None:
        wizard = CreateChestWizard(
            self.launcher.recipes, self.launcher._get_runners_list(), self.launcher
        )
        wizard.created.connect(self._on_chest_wizard_finish)
        wizard.exec()

    @Slot(str, str, str, bool)
    def _on_chest_wizard_finish(
        self, name: str, recipe_id: str, runner_name: str, sandbox_enabled: bool
    ) -> None:
        prefix_path = self.launcher.db.get_prefixes_dir() / name
        prefix_path.mkdir(parents=True, exist_ok=True)

        self.launcher.db.add_game(
            name=name.replace("_", " ").title(),
            exe="Contenedor de Sistema",
            runner=runner_name,
            prefix=name,
            recipe_id=recipe_id,
        )

        games = self.launcher.db.list_games()
        chest_placeholder = name.replace("_", " ").title()
        if chest_placeholder in games:
            games[chest_placeholder]["sandbox"] = sandbox_enabled
            self.launcher.db.save()

        env, runner_path = self.launcher.get_wine_env(name, recipe_id, runner_name)
        wine_exe = self.launcher._get_wine_cmd(runner_path)

        self.launcher.toast.show_message(_("main_toast_creating_chest", name=name))

        self.launcher.console_dialog = core.WinetricksConsoleDialog(
            _("main_wineboot_label"), name, self.launcher
        )
        self.launcher.console_dialog.setWindowTitle(_("main_creating_chest_title", name=name))

        self.launcher.process = QProcess()
        self.launcher.process.readyReadStandardOutput.connect(
            self.launcher.winetricks_ctrl._on_winetricks_stdout
        )
        self.launcher.process.readyReadStandardError.connect(
            self.launcher.winetricks_ctrl._on_winetricks_stderr
        )

        def _finish_handler(exit_code: int, exit_status: QProcess.ExitStatus):
            self._on_chest_init_finished(exit_code, name)

        self.launcher.process.finished.connect(_finish_handler)
        self.launcher.process.errorOccurred.connect(
            lambda err: self._on_chest_init_error(err, name)
        )

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

        wineserver_bin = (
            Path(wine_exe).parent / "wineserver"
            if Path(wine_exe).parent.name in ("bin", "files")
            else "wineserver"
        )
        cmd_str = f'"{wine_exe}" wineboot -u; "{wineserver_bin}" -w'

        self.launcher.process.start("bash", ["-c", cmd_str])
        self.launcher.console_dialog.show()

    def _on_chest_init_error(self, error: QProcess.ProcessError, name: str) -> None:
        print(f"[ChestInit Error] QProcess failed for '{name}': {error}")
        if self.launcher.console_dialog:
            self.launcher.console_dialog.console.append(_("main_init_error_console", error=error))
            self.launcher.console_dialog.btn_close.setEnabled(True)

    def _on_chest_init_finished(self, exit_code: int, name: str) -> None:
        if self.launcher.console_dialog:
            self.launcher.console_dialog.console.append(
                _("main_init_finished_console", exit_code=exit_code)
            )
            self.launcher.console_dialog.btn_close.setEnabled(True)

        if exit_code == 0:
            self.launcher.toast.show_message(_("main_toast_chest_created", name=name))
            self.launcher.refresh_data()
            self.launcher._on_chest_selected(name)
        else:
            QMessageBox.warning(
                self.launcher,
                _("main_init_warning_title"),
                _("main_init_warning_msg", name=name, exit_code=exit_code),
            )

    # ─── CHEST DETAILS ACTIONS ─────────────────────────────────────────────────

    @Slot(str)
    def _on_chest_run(self, prefix_name: str) -> None:
        game_to_run = None
        for gname, ginfo in self.launcher.db.list_games().items():
            if ginfo.get("prefix") == prefix_name and "Contenedor de Sistema" not in ginfo.get(
                "exe", ""
            ):
                game_to_run = gname
                break
        if game_to_run:
            self._on_chest_run_program(prefix_name, game_to_run)
        else:
            self.launcher.toast.show_message(_("main_toast_add_exe", prefix_name=prefix_name))

    @Slot(str)
    def _on_chest_browse(self, prefix_name: str) -> None:
        import subprocess

        prefix_path = self.launcher.db.get_prefixes_dir() / prefix_name
        drive_c = prefix_path / "drive_c"
        drive_c.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(drive_c)])
        except Exception as e:
            QMessageBox.critical(
                self.launcher, _("main_error_title"), _("main_error_open_folder", error=e)
            )

    @Slot(str)
    def _on_chest_terminal(self, prefix_name: str) -> None:
        import subprocess

        recipe_id = self._get_chest_recipe_id(prefix_name)
        env, _ = self.launcher.get_wine_env(prefix_name, recipe_id)

        default_term = self.launcher.db.data["global_config"].get(
            "default_terminal", "gnome-terminal"
        )
        sh_cmd = f"export WINEPREFIX='{env['WINEPREFIX']}'; export PATH='{env.get('PATH', '')}'; exec bash"

        try:
            if default_term == "konsole":
                subprocess.Popen(["konsole", "-e", "bash", "-c", sh_cmd])
            elif default_term in ["alacritty", "kitty"]:
                subprocess.Popen([default_term, "-e", "bash", "-c", sh_cmd])
            elif default_term == "xfce4-terminal":
                subprocess.Popen([default_term, "-e", f"bash -c '{sh_cmd}'"])
            elif default_term == "xterm":
                subprocess.Popen(["xterm", "-e", "bash", "-c", sh_cmd])
            else:
                subprocess.Popen(["gnome-terminal", "--", "bash", "-c", sh_cmd])
        except Exception as e:
            QMessageBox.critical(
                self.launcher,
                _("main_error_terminal_title"),
                _("main_error_terminal_msg", terminal=default_term, error=e),
            )

    @Slot(str)
    def _on_chest_rename(self, prefix_name: str) -> None:
        new_name, ok = QInputDialog.getText(
            self.launcher,
            _("main_rename_title"),
            _("main_rename_msg", prefix_name=prefix_name),
            QLineEdit.Normal,
            prefix_name,
        )
        if ok and new_name.strip():
            clean_new = new_name.strip().replace(" ", "_")
            if clean_new == prefix_name:
                return

            if self.launcher.db.rename_prefix(prefix_name, clean_new):
                self.launcher.refresh_data()
                update_system_context_menu(self.launcher.db.list_existing_prefixes())
                self.launcher._on_chest_selected(clean_new)
                self.launcher.toast.show_message(_("main_toast_renamed", name=clean_new))
            else:
                QMessageBox.warning(
                    self.launcher,
                    _("main_rename_failed_title"),
                    _("main_rename_failed_msg", name=clean_new),
                )

    @Slot(str)
    def _on_chest_delete(self, prefix_name: str) -> None:
        confirm = QMessageBox.question(
            self.launcher,
            _("main_delete_title"),
            _("main_delete_msg", prefix_name=prefix_name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            games_to_remove = [
                gname
                for gname, ginfo in self.launcher.db.list_games().items()
                if ginfo.get("prefix") == prefix_name
            ]
            for gname in games_to_remove:
                self.launcher.remove_launcher(prefix_name, gname)
                self.launcher.db.remove_game(gname)

            import shutil

            for p_dir in [
                self.launcher.db.get_prefixes_dir(),
                Path.home() / ".local" / "share" / "thatch" / "prefixes",
            ]:
                target = p_dir / prefix_name
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)

            self.launcher.refresh_data()
            self.launcher._on_sidebar_view_changed("chests")
            self.launcher.toast.show_message(_("main_toast_deleted", prefix_name=prefix_name))

    def _get_chest_recipe_id(self, prefix_name: str) -> str:
        for ginfo in self.launcher.db.list_games().values():
            if ginfo.get("prefix") == prefix_name:
                return ginfo.get("recipe_id", "default_gaming")
        return "default_gaming"

    @Slot(str)
    def _on_chest_add_program(self, prefix_name: str, exe_path_override: str | None = None) -> None:
        if exe_path_override:
            path = exe_path_override
        else:
            drive_c = self.launcher.db.get_prefixes_dir() / prefix_name / "drive_c"
            start_dir = str(drive_c) if drive_c.exists() else ""
            path, _filter = QFileDialog.getOpenFileName(
                self.launcher,
                _("main_recruit_dialog_title"),
                start_dir,
                "Executables (*.exe)",
            )

        if path:
            exe_file = Path(path)
            game_name, ok = QInputDialog.getText(
                self.launcher,
                _("main_game_name_title"),
                _("main_game_name_msg"),
                QLineEdit.Normal,
                exe_file.stem.replace("_", " ").title(),
            )
            if ok and game_name.strip():
                clean_game_name = game_name.strip()
                recipe_id = self._get_chest_recipe_id(prefix_name)
                runner = (
                    self.launcher.db.data["global_config"].get("default_runner")
                    or "Wine del Sistema (/usr/bin/wine)"
                )
                self.launcher.db.add_game(
                    name=clean_game_name,
                    exe=path,
                    runner=runner,
                    prefix=prefix_name,
                    recipe_id=recipe_id,
                )
                icon_path = self.launcher._extract_exe_icon(prefix_name, exe_file, clean_game_name)
                self.launcher.generate_launcher(prefix_name, clean_game_name, icon_path)
                self.launcher.refresh_data()
                self.launcher.toast.show_message(_("main_toast_recruited", name=clean_game_name))

    @Slot(str, str)
    def _on_chest_remove_link(self, prefix_name: str, game_name: str) -> None:
        confirm = QMessageBox.question(
            self.launcher,
            _("main_unlink_title"),
            _("main_unlink_msg", game_name=game_name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            self.launcher.remove_launcher(prefix_name, game_name)
            self.launcher.db.remove_game(game_name)
            self.launcher.refresh_data()
            self.launcher.toast.show_message(_("main_toast_unlinked", game_name=game_name))

    @Slot(str, str)
    def _on_chest_remove_program(self, prefix_name: str, game_name: str) -> None:
        game_info = self.launcher.db.get_game(game_name)
        if not game_info:
            return

        confirm = QMessageBox.question(
            self.launcher,
            _("main_uninstall_title"),
            _("main_uninstall_msg", game_name=game_name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            # Check if there is an uninstall string in Wine registry
            reg_programs = self.launcher.get_wine_installed_programs(prefix_name)
            uninst_str = ""
            for p in reg_programs:
                if p["name"].lower() == game_name.lower():
                    uninst_str = p.get("uninstall_string", "")
                    break

            if uninst_str:
                env, runner_path = self.launcher.get_wine_env(
                    prefix_name, game_info.get("recipe_id", "default_gaming")
                )
                wine_cmd = self.launcher._get_wine_cmd(runner_path)

                import subprocess

                try:
                    p_env = dict(sys.environ)
                    p_env.update(env)
                    subprocess.Popen(f'"{wine_cmd}" {uninst_str}', shell=True, env=p_env)
                    self.launcher.toast.show_message(
                        _("main_toast_uninstalling", game_name=game_name)
                    )
                except Exception as e:
                    self.launcher.toast.show_message(_("main_toast_uninstall_error", error=e))

            self.launcher.remove_launcher(prefix_name, game_name)
            self.launcher.db.remove_game(game_name)
            self.launcher.refresh_data()
            self.launcher.toast.show_message(_("main_toast_uninstalled", game_name=game_name))

    @Slot()
    def _on_manual_cleanup_orphans(self) -> None:
        count = self.launcher.cleanup_orphaned_launchers()
        if count > 0:
            self.launcher.toast.show_message(_("main_toast_orphans_cleaned", count=count))
        else:
            self.launcher.toast.show_message(_("main_toast_no_orphans"))

    @Slot()
    def register_context_menu(self) -> None:
        chests = self.launcher.db.list_existing_prefixes()
        success = update_system_context_menu(chests)
        if success:
            self.launcher.toast.show_message(_("toast_context_menu_registered"))
        else:
            self.launcher.toast.show_message(_("main_toast_context_menu_failed"))

    @Slot(str, str)
    def _on_link_registry_program(self, prefix_name: str, app_id: str) -> None:
        reg_programs = self.launcher.get_wine_installed_programs(prefix_name)
        target_app = next((p for p in reg_programs if p["id"] == app_id), None)
        if not target_app:
            self.launcher.toast.show_message(_("main_toast_reg_program_missing"))
            return

        game_name = target_app["name"]
        detected_exe = self.launcher.detect_game_exe(prefix_name, target_app)

        if not detected_exe:
            drive_c = self.launcher.db.get_prefixes_dir() / prefix_name / "drive_c"
            start_dir = (
                target_app.get("install_location")
                if target_app.get("install_location")
                and Path(target_app["install_location"]).exists()
                else str(drive_c)
            )
            path, _filter = QFileDialog.getOpenFileName(
                self.launcher,
                _("main_select_exe_title", game_name=game_name),
                start_dir,
                "Executables (*.exe)",
            )
            if path:
                detected_exe = Path(path)

        if detected_exe:
            recipe_id = self._get_chest_recipe_id(prefix_name)
            runner = (
                self.launcher.db.data["global_config"].get("default_runner")
                or "Wine del Sistema (/usr/bin/wine)"
            )
            self.launcher.db.add_game(
                name=game_name,
                exe=str(detected_exe),
                runner=runner,
                prefix=prefix_name,
                recipe_id=recipe_id,
            )
            icon_path = self.launcher._extract_exe_icon(prefix_name, detected_exe, game_name)
            self.launcher.generate_launcher(prefix_name, game_name, icon_path)
            self.launcher.refresh_data()
            self.launcher.toast.show_message(_("main_toast_linked", game_name=game_name))

    @Slot(str, str)
    def _on_chest_run_program(self, prefix_name: str, game_name: str) -> None:
        game_info = self.launcher.db.get_game(game_name)
        if not game_info:
            self.launcher.toast.show_message(_("main_toast_game_missing", game_name=game_name))
            return

        exe_path = Path(game_info.get("exe", ""))
        if not exe_path.exists():
            QMessageBox.warning(
                self.launcher,
                _("main_exe_missing_title"),
                _("main_exe_missing_msg", exe_path=exe_path),
            )
            return

        # Check for generated script launcher first
        from core.launchers import clean_game_name

        clean_name = clean_game_name(game_name)
        sh_launcher = (
            self.launcher.db.get_prefixes_dir() / prefix_name / "launchers" / f"{clean_name}.sh"
        )

        launch_mode = self.launcher.db.get_launch_mode()
        if launch_mode == "extreme":
            QTimer.singleShot(800, QApplication.quit)
        elif launch_mode == "stealth" and self.launcher.tray_icon:
            self.launcher.hide()

        import subprocess

        try:
            if sh_launcher.exists():
                subprocess.Popen(["bash", str(sh_launcher)])
            else:
                recipe_id = game_info.get("recipe_id", "default_gaming")
                env, runner_path = self.launcher.get_wine_env(
                    prefix_name, recipe_id, game_info.get("runner")
                )
                wine_cmd = self.launcher._get_wine_cmd(runner_path, exe_path)

                p_env = dict(sys.environ)
                p_env.update(env)

                game_dir = exe_path.parent
                relative_exe = exe_path.name
                if (
                    game_dir.name.lower() in ["x64", "bin64", "bin", "win64", "x86"]
                    and game_dir.parent.name.lower() != "drive_c"
                ):
                    game_dir = game_dir.parent
                    relative_exe = f"{exe_path.parent.name}/{exe_path.name}"

                vd_enabled = bool(game_info.get("virtual_desktop", False))
                vd_res = game_info.get("virtual_desktop_res", "1920x1080")

                if vd_enabled:
                    cmd_str = f'cd "{game_dir}" && "{wine_cmd}" explorer /desktop=Thatch,{vd_res} "{relative_exe}"'
                else:
                    cmd_str = f'cd "{game_dir}" && "{wine_cmd}" "{relative_exe}"'

                subprocess.Popen(cmd_str, shell=True, env=p_env)

            self.launcher.toast.show_message(_("main_toast_launching", game_name=game_name))
        except Exception as e:
            QMessageBox.critical(
                self.launcher, _("main_run_error_title"), _("main_run_error_msg", error=e)
            )

    # ─── CHEST SETTINGS & CONFIGURATION SLOTS ─────────────────────────────────

    @Slot(str, str)
    def _on_chest_runner_changed(self, prefix_name: str, runner_name: str) -> None:
        games = self.launcher.db.list_games()
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                ginfo["runner"] = runner_name
                icon_path = (
                    Path.home()
                    / ".local"
                    / "share"
                    / "icons"
                    / "thatch"
                    / prefix_name
                    / f"{gname.lower().replace(' ', '_')}.png"
                )
                self.launcher.generate_launcher(prefix_name, gname, icon_path)
        self.launcher.db.save()
        self.launcher.toast.show_message(
            _("main_toast_runner_changed", prefix_name=prefix_name, runner_name=runner_name)
        )

    @Slot(str, str, bool)
    def _on_chest_perf_settings_changed(
        self, prefix_name: str, recipe_id: str, sandbox_enabled: bool
    ) -> None:
        games = self.launcher.db.list_games()
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                ginfo["recipe_id"] = recipe_id
                ginfo["sandbox"] = sandbox_enabled
                icon_path = (
                    Path.home()
                    / ".local"
                    / "share"
                    / "icons"
                    / "thatch"
                    / prefix_name
                    / f"{gname.lower().replace(' ', '_')}.png"
                )
                self.launcher.generate_launcher(prefix_name, gname, icon_path)
        self.launcher.db.save()
        self.launcher.toast.show_message(_("main_toast_perf_saved", prefix_name=prefix_name))

    @Slot(str, bool, str)
    def _on_chest_virtual_desktop_changed(
        self, prefix_name: str, enabled: bool, resolution: str
    ) -> None:
        games = self.launcher.db.list_games()
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                ginfo["virtual_desktop"] = enabled
                ginfo["virtual_desktop_res"] = resolution
                icon_path = (
                    Path.home()
                    / ".local"
                    / "share"
                    / "icons"
                    / "thatch"
                    / prefix_name
                    / f"{gname.lower().replace(' ', '_')}.png"
                )
                self.launcher.generate_launcher(prefix_name, gname, icon_path)
        self.launcher.db.save()
        status = _("main_vd_on") if enabled else _("main_vd_off")
        self.launcher.toast.show_message(
            _("main_toast_vd", prefix_name=prefix_name, status=status, resolution=resolution)
        )

    @Slot(str, int)
    def _on_chest_dpi_scale_changed(self, prefix_name: str, dpi_val: int) -> None:
        games = self.launcher.db.list_games()
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                ginfo["dpi_scale"] = dpi_val
        self.launcher.db.save()
        self.launcher.toast.show_message(
            _("main_toast_dpi_saved", prefix_name=prefix_name, dpi_val=dpi_val)
        )

    @Slot(str, str)
    def _on_chest_monitor_changed(self, prefix_name: str, monitor_name: str) -> None:
        games = self.launcher.db.list_games()
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                ginfo["target_monitor"] = monitor_name
                icon_path = (
                    Path.home()
                    / ".local"
                    / "share"
                    / "icons"
                    / "thatch"
                    / prefix_name
                    / f"{gname.lower().replace(' ', '_')}.png"
                )
                self.launcher.generate_launcher(prefix_name, gname, icon_path)
        self.launcher.db.save()
        label = (
            _("main_monitor_default")
            if monitor_name == "default"
            else _("main_monitor_label", monitor_name=monitor_name)
        )
        self.launcher.toast.show_message(_("main_toast_monitor_saved", label=label))
