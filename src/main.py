#!/usr/bin/env python3
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QMessageBox,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QSystemTrayIcon,
    QMenu,
    QStackedWidget,
)
from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, Slot, Signal
from PySide6.QtGui import QIcon, QAction

# Import modular backend components
from database import ThatchDB
from hardware import detect_gpu
from desktop_integration import update_system_context_menu
from i18n import _, ACTIVE_LANG

# Import modular views package
from views import (
    UnifiedSidebar,
    ChestsView,
    ChestDetailsView,
    MapasView,
    PreferencesView,
    WineRunnersView,
    CreateChestWizard,
    ToastNotification,
    RecipesView,
)

# Import modular core services
import core

__version__ = "1.0.1"


# ─── MAIN COORDINATOR WINDOW: THATCHLAUNCHER ──────────────────────────────────


class ThatchLauncher(QMainWindow):
    """
    Main coordinator window linking the layout architecture
    with database, views, and core Wine execution services.
    """

    _catalog_ready = Signal(int)
    _catalog_failed = Signal()
    _catalog_error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"🏴‍☠️ Thatch - {_('app_title')} v{__version__}")
        self.resize(1000, 680)

        # Initialize databases & hardware probes
        self.db = ThatchDB()
        self.recipes = self.db.load_recipes()
        self.active_gpu = detect_gpu()

        self.process = None
        self.current_prefix = ""
        self.current_verb = ""
        self.console_dialog = None
        self.tray_icon = None
        self.is_installer_mode = False
        self._winetricks_catalog: list[dict] | None = None  # lazy cache

        # Connect background catalog signals
        self._catalog_ready.connect(self._on_catalog_ready)
        self._catalog_failed.connect(self._on_catalog_failed)
        self._catalog_error.connect(self._on_catalog_error)

        self.init_tray()
        self.init_ui()
        self.refresh_data()
        self.handle_cli_args()

    def init_tray(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            from PySide6.QtGui import QPixmap, QColor

            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor("#00e676"))
            self.tray_icon.setIcon(QIcon(pixmap))

            tray_menu = QMenu()
            show_title = "Show Thatch" if ACTIVE_LANG == "en" else "Mostrar Thatch"
            quit_title = "Exit" if ACTIVE_LANG == "en" else "Salir"

            show_action = QAction(show_title, self)
            show_action.triggered.connect(self.showNormal)
            quit_action = QAction(quit_title, self)
            quit_action.triggered.connect(QApplication.quit)

            tray_menu.addAction(show_action)
            tray_menu.addAction(quit_action)
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self._on_tray_activated)
            self.tray_icon.show()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()

    def init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Sidebar Navigation (Left)
        self.sidebar = UnifiedSidebar(self)
        self.sidebar.view_changed.connect(self._on_sidebar_view_changed)
        main_layout.addWidget(self.sidebar)

        # 2. Main Stacked Widget Area (Right)
        self.view_stack = QStackedWidget(self)
        main_layout.addWidget(self.view_stack, stretch=1)

        # View 0: Chests View
        self.chests_view = ChestsView(self)
        self.chests_view.create_requested.connect(self._on_create_chest_requested)
        self.chests_view.chest_selected.connect(self._on_chest_selected)
        self.view_stack.addWidget(self.chests_view)

        # View 1: Chest Details View
        self.chest_details_view = ChestDetailsView(self.active_gpu, self)
        self.chest_details_view.back_requested.connect(
            lambda: self._on_sidebar_view_changed("chests")
        )
        self.chest_details_view.run_requested.connect(self._on_chest_run)
        self.chest_details_view.browse_requested.connect(self._on_chest_browse)
        self.chest_details_view.terminal_requested.connect(self._on_chest_terminal)
        self.chest_details_view.rename_requested.connect(self._on_chest_rename)
        self.chest_details_view.delete_requested.connect(self._on_chest_delete)
        self.chest_details_view.add_program_requested.connect(self._on_chest_add_program)
        self.chest_details_view.run_program_requested.connect(self._on_chest_run_program)
        self.chest_details_view.remove_program_requested.connect(self._on_chest_remove_program)
        self.chest_details_view.remove_link_requested.connect(self._on_chest_remove_link)
        self.chest_details_view.run_installer_requested.connect(self._on_chest_run_installer)
        self.chest_details_view.install_dependency_requested.connect(
            self._on_chest_install_dependency
        )
        self.chest_details_view.remove_dependency_requested.connect(
            self._on_chest_remove_dependency
        )
        self.chest_details_view.runner_changed.connect(self._on_chest_runner_changed)
        self.chest_details_view.perf_settings_changed.connect(self._on_chest_perf_settings_changed)
        self.chest_details_view.virtual_desktop_changed.connect(
            self._on_chest_virtual_desktop_changed
        )
        self.chest_details_view.dpi_scale_changed.connect(self._on_chest_dpi_scale_changed)
        self.chest_details_view.monitor_changed.connect(self._on_chest_monitor_changed)
        self.chest_details_view.link_registry_program_requested.connect(
            self._on_link_registry_program
        )
        self.view_stack.addWidget(self.chest_details_view)

        # View 2: Cargo View (Mapas)
        self.cargo_view = MapasView(self)
        self.cargo_view.install_requested.connect(self._on_cargo_install_requested)
        self.cargo_view.map_deleted.connect(self.refresh_data)
        self.view_stack.addWidget(self.cargo_view)

        # View 3: Preferences View
        self.preferences_view = PreferencesView(self.db, self._get_runners_list(), self)
        self.preferences_view.toast_requested.connect(self._on_toast_requested)
        self.preferences_view.update_catalog_requested.connect(self._on_update_catalog_requested)
        self.preferences_view.cleanup_orphans_requested.connect(self._on_manual_cleanup_orphans)
        self.preferences_view.register_context_menu_requested.connect(self.register_context_menu)
        self.preferences_view.combo_language.currentIndexChanged.connect(self.on_language_changed)
        self.view_stack.addWidget(self.preferences_view)

        # View 4: Wine Runners View
        self.wine_runners_view = WineRunnersView(self.db, self._get_runners_list(), self)
        self.wine_runners_view.runner_downloaded.connect(self._on_runner_downloaded)
        self.wine_runners_view.toast_requested.connect(self._on_toast_requested)
        self.view_stack.addWidget(self.wine_runners_view)

        # View 5: Recipes View (Mapas)
        recipes_dir = self.db.recipes_dir
        self.recipes_view = RecipesView(recipes_dir, self)
        self.view_stack.addWidget(self.recipes_view)

        # 3. Toast Overlay
        self.toast = ToastNotification(self)

        # 4. Clean up orphaned desktop shortcuts
        self.cleanup_orphaned_launchers()

    # ─── CORE DELEGATE PROXIES ────────────────────────────────────────────────

    def get_wine_env(
        self, prefix_name: str, recipe_id: str, runner_override: str | None = None
    ) -> tuple[dict[str, str], Path | None]:
        return core.get_wine_env(
            self.db,
            self.active_gpu,
            self.recipes,
            prefix_name,
            recipe_id,
            runner_override,
        )

    def _get_pe_arch(self, exe_path: str | Path) -> str:
        return core.get_pe_arch(exe_path)

    def _get_wine_cmd(self, runner_path, exe_path: str | Path | None = None) -> str:
        return core.get_wine_cmd(self.db, runner_path, exe_path)

    def win_to_linux_path(self, prefix_name: str, win_path: str) -> Path | None:
        return core.win_to_linux_path(self.db, prefix_name, win_path)

    def get_wine_installed_programs(self, prefix_name: str) -> list[dict]:
        return core.get_wine_installed_programs(self.db.get_prefixes_dir(), prefix_name)

    def detect_game_exe(self, prefix_name: str, reg_entry: dict) -> Path | None:
        return core.detect_game_exe(self.db, prefix_name, reg_entry)

    def generate_launcher(
        self, prefix_name: str, game_name: str, icon_path: Path | None = None
    ) -> None:
        core.generate_launcher(
            self.db, self.active_gpu, self.recipes, prefix_name, game_name, icon_path
        )

    def remove_launcher(self, prefix_name: str, game_name: str) -> None:
        core.remove_launcher(self.db, prefix_name, game_name)

    def cleanup_orphaned_launchers(self) -> int:
        return core.cleanup_orphaned_launchers(self.db)

    def _extract_exe_icon(self, prefix_name: str, exe_path: Path, game_name: str) -> Path | None:
        return core.extract_exe_icon(prefix_name, exe_path, game_name)

    def handle_cli_args(self) -> None:
        core.handle_cli_args(self)

    def prompt_installer_launch(self, installer_path: str, target_chest: str | None = None) -> None:
        core.prompt_installer_launch(self, installer_path, target_chest)

    @Slot(str, str)
    def _on_chest_run_installer(self, prefix_name: str, installer_path: str) -> None:
        core.run_chest_installer(self, prefix_name, installer_path)

    def _show_post_installer_dialog(self, prefix_name: str) -> None:
        core.show_post_installer_dialog(self, prefix_name)

    # ─── WINETRICKS CATALOG SERVICES ──────────────────────────────────────────

    def load_winetricks_catalog(self) -> list[dict]:
        if self._winetricks_catalog is not None:
            return self._winetricks_catalog

        try:
            cached = self.db.get_winetricks_catalog()
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
            self.db,
            self._catalog_ready,
            self._catalog_failed,
            self._catalog_error,
            silent=silent,
        )

    @Slot(int)
    def _on_catalog_ready(self, count: int) -> None:
        self.toast.show_message(_("toast_catalog_updated", count=count))
        self.refresh_data()

    @Slot()
    def _on_catalog_failed(self) -> None:
        self.toast.show_message(_("toast_catalog_failed"))

    @Slot(str)
    def _on_catalog_error(self, message: str) -> None:
        self.toast.show_message(message)

    @Slot()
    def _on_update_catalog_requested(self) -> None:
        self.toast.show_message(_("toast_catalog_updating"))
        self._trigger_winetricks_catalog_refresh(silent=False)

    def _get_runners_list(self) -> list[str]:
        runners_dir = self.db.get_runners_dir()
        names = set()
        if runners_dir.exists():
            names.update(
                d.name
                for d in runners_dir.iterdir()
                if d.is_dir() and "aarch64" not in d.name.lower() and "arm64" not in d.name.lower()
            )
        # Motores de sistema (compat tools de Steam: proton-cachyos-slr, etc.)
        from core.wine import discover_system_runners

        names.update(name for name, _ in discover_system_runners())
        return sorted(names)

    def refresh_data(self) -> None:
        """Reloads active lists across all widgets."""
        prefixes = self.db.list_existing_prefixes()
        games = self.db.list_games()
        runners = self._get_runners_list()

        updated_db = False
        for prefix_name in prefixes:
            primary_recipe = None
            for gname, ginfo in games.items():
                if ginfo.get("prefix") == prefix_name and "Contenedor de Sistema" in ginfo.get(
                    "exe", ""
                ):
                    primary_recipe = ginfo.get("recipe_id")
                    break
            if primary_recipe and primary_recipe != "default_gaming":
                for gname, ginfo in games.items():
                    if (
                        ginfo.get("prefix") == prefix_name
                        and ginfo.get("recipe_id") == "default_gaming"
                    ):
                        ginfo["recipe_id"] = primary_recipe
                        updated_db = True
        if updated_db:
            self.db.save()
            games = self.db.list_games()

        self.chests_view.populate_chests(prefixes, games, self.recipes, self.db.get_prefixes_dir())
        self.cargo_view.populate_maps(prefixes, self.recipes)
        self.preferences_view.update_runners_list(runners)
        self.wine_runners_view.update_runners_list(runners)

        try:
            update_system_context_menu(prefixes)
        except Exception as e:
            print(f"Failed to auto-update system context menu: {e}")

        if self.chest_details_view.prefix_name:
            installed = self.get_installed_verbs(self.chest_details_view.prefix_name)
            registry_programs = self.get_wine_installed_programs(
                self.chest_details_view.prefix_name
            )
            self.chest_details_view.update_view(
                self.chest_details_view.prefix_name,
                games,
                self.recipes,
                installed,
                runners,
                self.db.get_prefixes_dir(),
                registry_programs=registry_programs,
                catalog=self.load_winetricks_catalog(),
            )

    def get_installed_verbs(self, prefix_name: str) -> list[str]:
        prefix_path = self.db.get_prefixes_dir() / prefix_name
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
        prefix_path = self.db.get_prefixes_dir() / prefix_name
        log_path = prefix_path / "winetricks.log"
        prefix_path.mkdir(parents=True, exist_ok=True)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"w_workaround {verb}\n")
        except Exception as e:
            print(f"Error writing winetricks.log: {e}")

    # ─── SIDEBAR EVENT HANDLERS ────────────────────────────────────────────────

    @Slot(str)
    def _on_sidebar_view_changed(self, view_name: str) -> None:
        view_map = {
            "chests": 0,
            "chest_details": 1,
            "cargo": 2,
            "preferences": 3,
            "wine_runners": 4,
            "runners": 4,
            "recipes": 5,
        }
        idx = view_map.get(view_name, 0)
        self.view_stack.setCurrentIndex(idx)
        if view_name != "chest_details":
            self.chest_details_view.prefix_name = ""

    # ─── CHESTS GRID VIEW ACTIONS ──────────────────────────────────────────────

    @Slot()
    def _on_create_chest_requested(self) -> None:
        wizard = CreateChestWizard(self.recipes, self._get_runners_list(), self)
        wizard.created.connect(self._on_chest_wizard_finish)
        wizard.exec()

    @Slot(str, str, str, bool)
    def _on_chest_wizard_finish(
        self, name: str, recipe_id: str, runner_name: str, sandbox_enabled: bool
    ) -> None:
        prefix_path = self.db.get_prefixes_dir() / name
        prefix_path.mkdir(parents=True, exist_ok=True)

        self.db.add_game(
            name=name.replace("_", " ").title(),
            exe="Contenedor de Sistema",
            runner=runner_name,
            prefix=name,
            recipe_id=recipe_id,
        )

        games = self.db.list_games()
        chest_placeholder = name.replace("_", " ").title()
        if chest_placeholder in games:
            games[chest_placeholder]["sandbox"] = sandbox_enabled
            self.db.save()

        env, runner_path = self.get_wine_env(name, recipe_id, runner_name)
        wine_exe = self._get_wine_cmd(runner_path)

        self.toast.show_message(f"Creando e inicializando contenedor de Wine para '{name}'...")

        self.console_dialog = core.WinetricksConsoleDialog(
            "wineboot (Inicialización de Sistema)", name, self
        )
        self.console_dialog.setWindowTitle(f"Creating Chest: {name}")

        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self._on_winetricks_stdout)
        self.process.readyReadStandardError.connect(self._on_winetricks_stderr)

        def _finish_handler(exit_code: int, exit_status: QProcess.ExitStatus):
            self._on_chest_init_finished(exit_code, name)

        self.process.finished.connect(_finish_handler)
        self.process.errorOccurred.connect(lambda err: self._on_chest_init_error(err, name))

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

        recipe_obj = self.recipes.get(recipe_id, {})
        recipe_perf = recipe_obj.get("performance_env", {})
        if recipe_perf.get("WINEARCH") == "win64" or recipe_perf.get("WINEARCH64"):
            q_env.insert("WINEARCH", "win64")

        self.process.setProcessEnvironment(q_env)

        wineserver_bin = (
            Path(wine_exe).parent / "wineserver"
            if Path(wine_exe).parent.name in ("bin", "files")
            else "wineserver"
        )
        cmd_str = f'"{wine_exe}" wineboot -u; "{wineserver_bin}" -w'

        self.process.start("bash", ["-c", cmd_str])
        self.console_dialog.show()

    def _on_chest_init_error(self, error: QProcess.ProcessError, name: str) -> None:
        print(f"[ChestInit Error] QProcess failed for '{name}': {error}")
        if self.console_dialog:
            self.console_dialog.console.append(
                f"\n❌ ERROR: System initialization process failed to launch: {error}"
            )
            self.console_dialog.btn_close.setEnabled(True)

    def _on_chest_init_finished(self, exit_code: int, name: str) -> None:
        if self.console_dialog:
            self.console_dialog.console.append(
                f"\n✔ Chest system initialization finished (code {exit_code})."
            )
            self.console_dialog.btn_close.setEnabled(True)

        if exit_code == 0:
            self.toast.show_message(f"¡Contenedor '{name}' creado con éxito!")
            self.refresh_data()
            self._on_chest_selected(name)
        else:
            QMessageBox.warning(
                self,
                "Advertencia de Inicialización",
                f"El contenedor '{name}' fue creado pero el proceso wineboot finalizó con código {exit_code}.",
            )

    @Slot(str)
    def _on_chest_selected(self, prefix_name: str) -> None:
        games = self.db.list_games()
        runners = self._get_runners_list()
        installed = self.get_installed_verbs(prefix_name)
        registry_programs = self.get_wine_installed_programs(prefix_name)

        self.chest_details_view.update_view(
            prefix_name,
            games,
            self.recipes,
            installed,
            runners,
            self.db.get_prefixes_dir(),
            registry_programs=registry_programs,
            catalog=self.load_winetricks_catalog(),
        )
        if hasattr(self.sidebar, "btn_chest_details"):
            self.sidebar.btn_chest_details.setText(f"📦  {prefix_name.replace('_', ' ').title()}")
        self._on_sidebar_view_changed("chest_details")

    # ─── CHEST DETAILS ACTIONS ─────────────────────────────────────────────────

    @Slot(str)
    def _on_chest_run(self, prefix_name: str) -> None:
        game_to_run = None
        for gname, ginfo in self.db.list_games().items():
            if ginfo.get("prefix") == prefix_name and "Contenedor de Sistema" not in ginfo.get(
                "exe", ""
            ):
                game_to_run = gname
                break
        if game_to_run:
            self._on_chest_run_program(prefix_name, game_to_run)
        else:
            self.toast.show_message(
                f"Contenedor '{prefix_name}': Añade un ejecutable usando 'Reclutar Juego'."
            )

    @Slot(str)
    def _on_chest_browse(self, prefix_name: str) -> None:
        import subprocess

        prefix_path = self.db.get_prefixes_dir() / prefix_name
        drive_c = prefix_path / "drive_c"
        drive_c.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(drive_c)])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Fallo al abrir carpeta: {e}")

    @Slot(str)
    def _on_chest_terminal(self, prefix_name: str) -> None:
        import subprocess

        recipe_id = self._get_chest_recipe_id(prefix_name)
        env, _ = self.get_wine_env(prefix_name, recipe_id)

        default_term = self.db.data["global_config"].get("default_terminal", "gnome-terminal")
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
                self, "Error Terminal", f"Fallo al abrir terminal '{default_term}': {e}"
            )

    @Slot(str)
    def _on_chest_rename(self, prefix_name: str) -> None:
        from PySide6.QtWidgets import QInputDialog, QLineEdit

        new_name, ok = QInputDialog.getText(
            self,
            "Renombrar Cofre",
            f"Introduce el nuevo nombre para el cofre '{prefix_name}':",
            QLineEdit.Normal,
            prefix_name,
        )
        if ok and new_name.strip():
            clean_new = new_name.strip().replace(" ", "_")
            if clean_new == prefix_name:
                return

            if self.db.rename_prefix(prefix_name, clean_new):
                self.refresh_data()
                self.update_system_context_menu()
                self._on_chest_selected(clean_new)
                self.toast.show_message(f"¡Cofre renombrado exitosamente a '{clean_new}'!")
            else:
                QMessageBox.warning(
                    self,
                    "Error de Renombrado",
                    f"No se pudo renombrar el cofre a '{clean_new}'. Verifica que el nombre no exista ya.",
                )

    @Slot(str)
    def _on_chest_delete(self, prefix_name: str) -> None:
        confirm = QMessageBox.question(
            self,
            "Eliminar Contenedor",
            f"¿Seguro que deseas eliminar el contenedor '{prefix_name}'?\nEsto eliminará permanentemente la carpeta del prefijo.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            games_to_remove = [
                gname
                for gname, ginfo in self.db.list_games().items()
                if ginfo.get("prefix") == prefix_name
            ]
            for gname in games_to_remove:
                self.remove_launcher(prefix_name, gname)
                self.db.remove_game(gname)

            import shutil

            for p_dir in [
                self.db.get_prefixes_dir(),
                Path.home() / ".local" / "share" / "thatch" / "prefixes",
            ]:
                target = p_dir / prefix_name
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)

            self.refresh_data()
            self._on_sidebar_view_changed("chests")
            self.toast.show_message(f"Contenedor '{prefix_name}' eliminado con éxito.")

    def _get_chest_recipe_id(self, prefix_name: str) -> str:
        for ginfo in self.db.list_games().values():
            if ginfo.get("prefix") == prefix_name:
                return ginfo.get("recipe_id", "default_gaming")
        return "default_gaming"

    @Slot(str)
    def _on_chest_add_program(self, prefix_name: str, exe_path_override: str | None = None) -> None:
        if exe_path_override:
            path = exe_path_override
        else:
            drive_c = self.db.get_prefixes_dir() / prefix_name / "drive_c"
            start_dir = str(drive_c) if drive_c.exists() else ""
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Reclutar Juego (.exe)",
                start_dir,
                "Executables (*.exe)",
            )

        if path:
            exe_file = Path(path)
            game_name, ok = QInputDialog.getText(
                self,
                "Nombre del Juego",
                "Ingresa el nombre para mostrar en la biblioteca:",
                QLineEdit.Normal,
                exe_file.stem.replace("_", " ").title(),
            )
            if ok and game_name.strip():
                clean_game_name = game_name.strip()
                recipe_id = self._get_chest_recipe_id(prefix_name)
                runner = (
                    self.db.data["global_config"].get("default_runner")
                    or "Wine del Sistema (/usr/bin/wine)"
                )
                self.db.add_game(
                    name=clean_game_name,
                    exe=path,
                    runner=runner,
                    prefix=prefix_name,
                    recipe_id=recipe_id,
                )
                icon_path = self._extract_exe_icon(prefix_name, exe_file, clean_game_name)
                self.generate_launcher(prefix_name, clean_game_name, icon_path)
                self.refresh_data()
                self.toast.show_message(
                    f"¡Juego '{clean_game_name}' reclutado y lanzador generado con éxito!"
                )

    @Slot(str, str)
    def _on_chest_remove_link(self, prefix_name: str, game_name: str) -> None:
        confirm = QMessageBox.question(
            self,
            "Desvincular Juego",
            f"¿Deseas desvincular '{game_name}' de Thatch?\n\nLos archivos instalados en C:\\ NO se borrarán.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            self.remove_launcher(prefix_name, game_name)
            self.db.remove_game(game_name)
            self.refresh_data()
            self.toast.show_message(f"Juego '{game_name}' desvinculado.")

    @Slot(str, str)
    def _on_chest_remove_program(self, prefix_name: str, game_name: str) -> None:
        game_info = self.db.get_game(game_name)
        if not game_info:
            return

        confirm = QMessageBox.question(
            self,
            "Desinstalar Programa",
            f"¿Deseas intentar ejecutar el desinstalador de '{game_name}' y eliminar sus accesos directos?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            # Check if there is an uninstall string in Wine registry
            reg_programs = self.get_wine_installed_programs(prefix_name)
            uninst_str = ""
            for p in reg_programs:
                if p["name"].lower() == game_name.lower():
                    uninst_str = p.get("uninstall_string", "")
                    break

            if uninst_str:
                env, runner_path = self.get_wine_env(
                    prefix_name, game_info.get("recipe_id", "default_gaming")
                )
                wine_cmd = self._get_wine_cmd(runner_path)

                import subprocess

                try:
                    p_env = dict(sys.environ)
                    p_env.update(env)
                    subprocess.Popen(f'"{wine_cmd}" {uninst_str}', shell=True, env=p_env)
                    self.toast.show_message(f"Ejecutando desinstalador de '{game_name}'...")
                except Exception as e:
                    self.toast.show_message(f"Error al ejecutar desinstalador: {e}")

            self.remove_launcher(prefix_name, game_name)
            self.db.remove_game(game_name)
            self.refresh_data()
            self.toast.show_message(
                f"¡Programa '{game_name}' desinstalado y lanzadores eliminados!"
            )

    @Slot()
    def _on_manual_cleanup_orphans(self) -> None:
        count = self.cleanup_orphaned_launchers()
        if count > 0:
            self.toast.show_message(f"¡Se limpiaron {count} accesos directos huérfanos del panel!")
        else:
            self.toast.show_message("No se encontraron accesos directos huérfanos.")

    @Slot()
    def register_context_menu(self) -> None:
        chests = self.db.list_existing_prefixes()
        success = update_system_context_menu(chests)
        if success:
            self.toast.show_message(_("toast_context_menu_registered"))
        else:
            self.toast.show_message("Error al registrar menú contextual.")

    @Slot(str, str)
    def _on_link_registry_program(self, prefix_name: str, app_id: str) -> None:
        reg_programs = self.get_wine_installed_programs(prefix_name)
        target_app = next((p for p in reg_programs if p["id"] == app_id), None)
        if not target_app:
            self.toast.show_message("Error: Programa no encontrado en el registro.")
            return

        game_name = target_app["name"]
        detected_exe = self.detect_game_exe(prefix_name, target_app)

        if not detected_exe:
            drive_c = self.db.get_prefixes_dir() / prefix_name / "drive_c"
            start_dir = (
                target_app.get("install_location")
                if target_app.get("install_location")
                and Path(target_app["install_location"]).exists()
                else str(drive_c)
            )
            path, _ = QFileDialog.getOpenFileName(
                self,
                f"Seleccionar ejecutable para {game_name}",
                start_dir,
                "Executables (*.exe)",
            )
            if path:
                detected_exe = Path(path)

        if detected_exe:
            recipe_id = self._get_chest_recipe_id(prefix_name)
            runner = (
                self.db.data["global_config"].get("default_runner")
                or "Wine del Sistema (/usr/bin/wine)"
            )
            self.db.add_game(
                name=game_name,
                exe=str(detected_exe),
                runner=runner,
                prefix=prefix_name,
                recipe_id=recipe_id,
            )
            icon_path = self._extract_exe_icon(prefix_name, detected_exe, game_name)
            self.generate_launcher(prefix_name, game_name, icon_path)
            self.refresh_data()
            self.toast.show_message(f"¡'{game_name}' vinculado y lanzador generado con éxito!")

    @Slot(str, str)
    def _on_chest_run_program(self, prefix_name: str, game_name: str) -> None:
        game_info = self.db.get_game(game_name)
        if not game_info:
            self.toast.show_message(f"Error: Juego '{game_name}' no encontrado.")
            return

        exe_path = Path(game_info.get("exe", ""))
        if not exe_path.exists():
            QMessageBox.warning(
                self,
                "Ejecutable no encontrado",
                f"El ejecutable del juego no existe en:\n{exe_path}\n\nVerifica si la carpeta del juego fue movida.",
            )
            return

        # Check for generated script launcher first
        from core.launchers import clean_game_name

        clean_name = clean_game_name(game_name)
        sh_launcher = self.db.get_prefixes_dir() / prefix_name / "launchers" / f"{clean_name}.sh"

        launch_mode = self.db.get_launch_mode()
        if launch_mode == "extreme":
            QTimer.singleShot(800, QApplication.quit)
        elif launch_mode == "stealth" and self.tray_icon:
            self.hide()

        import subprocess

        try:
            if sh_launcher.exists():
                subprocess.Popen(["bash", str(sh_launcher)])
            else:
                recipe_id = game_info.get("recipe_id", "default_gaming")
                env, runner_path = self.get_wine_env(
                    prefix_name, recipe_id, game_info.get("runner")
                )
                wine_cmd = self._get_wine_cmd(runner_path, exe_path)

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

            self.toast.show_message(f"Lanzando '{game_name}'...")
        except Exception as e:
            QMessageBox.critical(self, "Error de Ejecución", f"Fallo al iniciar el juego: {e}")

    # ─── CHEST SETTINGS & CONFIGURATION SLOTS ─────────────────────────────────

    @Slot(str, str)
    def _on_chest_runner_changed(self, prefix_name: str, runner_name: str) -> None:
        games = self.db.list_games()
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
                self.generate_launcher(prefix_name, gname, icon_path)
        self.db.save()
        self.toast.show_message(f"Motor de Wine para '{prefix_name}' actualizado a: {runner_name}")

    @Slot(str, str, bool)
    def _on_chest_perf_settings_changed(
        self, prefix_name: str, recipe_id: str, sandbox_enabled: bool
    ) -> None:
        games = self.db.list_games()
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
                self.generate_launcher(prefix_name, gname, icon_path)
        self.db.save()
        self.toast.show_message(f"Ajustes de rendimiento y sandbox para '{prefix_name}' guardados.")

    @Slot(str, bool, str)
    def _on_chest_virtual_desktop_changed(
        self, prefix_name: str, enabled: bool, resolution: str
    ) -> None:
        games = self.db.list_games()
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
                self.generate_launcher(prefix_name, gname, icon_path)
        self.db.save()
        status = "activado" if enabled else "desactivado"
        self.toast.show_message(f"Escritorio Virtual para '{prefix_name}' {status} ({resolution}).")

    @Slot(str, int)
    def _on_chest_dpi_scale_changed(self, prefix_name: str, dpi_val: int) -> None:
        games = self.db.list_games()
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                ginfo["dpi_scale"] = dpi_val
        self.db.save()
        self.toast.show_message(f"Escala DPI para '{prefix_name}' guardada ({dpi_val} DPI).")

    @Slot(str, str)
    def _on_chest_monitor_changed(self, prefix_name: str, monitor_name: str) -> None:
        games = self.db.list_games()
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
                self.generate_launcher(prefix_name, gname, icon_path)
        self.db.save()
        label = "Por defecto" if monitor_name == "default" else f"Pantalla: {monitor_name}"
        self.toast.show_message(
            f"Pantalla de lanzamiento guardada: {label}. Lanzadores regenerados."
        )

    # ─── WINETRICKS DEPENDENCY INJECTIONS ──────────────────────────────────────

    @Slot(str, str)
    def _on_chest_install_dependency(self, prefix_name: str, verb: str) -> None:
        self._queue_winetricks_injections(prefix_name, [verb])

    @Slot(str, str)
    def _on_chest_remove_dependency(self, prefix_name: str, verb: str) -> None:
        prefix_path = self.db.get_prefixes_dir() / prefix_name
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
                self.toast.show_message(f"Componente '{verb}' removido del registro de Winetricks.")
                self.refresh_data()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Fallo al remover componente de log: {e}")

    def _queue_winetricks_injections(self, prefix_name: str, verbs: list[str]) -> None:
        if not hasattr(self, "winetricks_queue"):
            self.winetricks_queue = []
            self.winetricks_queue_prefix = ""

        self.winetricks_queue.extend(verbs)
        self.winetricks_queue_prefix = prefix_name

        if not (self.process and self.process.state() == QProcess.Running):
            self._process_next_winetricks_queue()

    def _process_next_winetricks_queue(self) -> None:
        if not getattr(self, "winetricks_queue", None):
            return

        verb = self.winetricks_queue.pop(0)
        prefix_name = self.winetricks_queue_prefix
        recipe_id = self._get_chest_recipe_id(prefix_name)

        env, runner_path = self.get_wine_env(prefix_name, recipe_id)
        wine_exe = self._get_wine_cmd(runner_path)

        self.current_prefix = prefix_name
        self.current_verb = verb

        self.console_dialog = core.WinetricksConsoleDialog(verb, prefix_name, self)

        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self._on_winetricks_stdout)
        self.process.readyReadStandardError.connect(self._on_winetricks_stderr)

        def _finish_handler(exit_code: int, exit_status: QProcess.ExitStatus):
            self._on_winetricks_finished(exit_code, prefix_name, verb)

        self.process.finished.connect(_finish_handler)
        self.process.errorOccurred.connect(self._on_winetricks_error)

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

        recipe_obj = self.recipes.get(recipe_id, {})
        recipe_perf = recipe_obj.get("performance_env", {})
        if recipe_perf.get("WINEARCH") == "win64" or recipe_perf.get("WINEARCH64"):
            q_env.insert("WINEARCH", "win64")

        self.process.setProcessEnvironment(q_env)

        import shutil

        if not shutil.which("winetricks"):
            QMessageBox.critical(
                self,
                "Error",
                "No se encontró 'winetricks' instalado en el sistema Linux host.",
            )
            return

        wineserver_bin = (
            Path(wine_exe).parent / "wineserver"
            if Path(wine_exe).parent.name in ("bin", "files")
            else "wineserver"
        )
        cmd_str = f'winetricks -q {verb}; "{wine_exe}" wineboot -u; "{wineserver_bin}" -w'

        self.process.start("bash", ["-c", cmd_str])
        self.console_dialog.show()

    def _on_winetricks_stdout(self) -> None:
        if self.process and self.console_dialog:
            data = self.process.readAllStandardOutput().data().decode("utf-8", errors="ignore")
            self.console_dialog.console.append(data)

    def _on_winetricks_stderr(self) -> None:
        if self.process and self.console_dialog:
            data = self.process.readAllStandardError().data().decode("utf-8", errors="ignore")
            self.console_dialog.console.append(data)

    def _on_winetricks_error(self, error: QProcess.ProcessError) -> None:
        print(f"[Winetricks Error] QProcess failed: {error}")
        if self.console_dialog:
            self.console_dialog.console.append(
                f"\n❌ ERROR: Winetricks process failed to launch: {error}"
            )
            self.console_dialog.btn_close.setEnabled(True)

    def _on_winetricks_finished(self, exit_code: int, prefix_name: str, verb: str) -> None:
        if self.console_dialog:
            self.console_dialog.console.append(
                f"\n✔ Winetricks process finished (code {exit_code})."
            )
            self.console_dialog.btn_close.setEnabled(True)

        if exit_code == 0:
            self.register_installed_verb(prefix_name, verb)
            self.toast.show_message(f"¡Componente '{verb}' inyectado con éxito!")
            self.refresh_data()
        else:
            QMessageBox.warning(
                self,
                "Inyección Fallida",
                f"Winetricks finalizó con código {exit_code} al instalar '{verb}'.",
            )

        if getattr(self, "winetricks_queue", None):
            QTimer.singleShot(300, self._process_next_winetricks_queue)

    # ─── CARGO VIEW (MAPAS) SLOTS ─────────────────────────────────────────────

    @Slot(str, str)
    def _on_cargo_install_requested(self, prefix_name: str, recipe_id: str) -> None:
        recipe = self.recipes.get(recipe_id, {})
        verbs = recipe.get("required_verbs", [])

        if not verbs:
            self.toast.show_message(
                f"La receta '{recipe.get('display_name', recipe_id)}' no requiere componentes adicionales de winetricks."
            )
            return

        installed = self.get_installed_verbs(prefix_name)
        to_install = [v for v in verbs if v not in installed]

        if not to_install:
            self.toast.show_message(
                f"Todos los componentes de '{recipe.get('display_name', recipe_id)}' ya están instalados en '{prefix_name}'."
            )
            return

        self._queue_winetricks_injections(prefix_name, to_install)

    # ─── OTHER EVENT HANDLERS ──────────────────────────────────────────────────

    @Slot()
    def on_language_changed(self) -> None:
        lang_data = self.preferences_view.combo_language.currentData()
        if lang_data:
            from i18n import set_active_lang

            set_active_lang(lang_data)
            self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(f"🏴‍☠️ Thatch - {_('app_title')} v{__version__}")
        self.sidebar.retranslate()
        self.chests_view.retranslate()
        self.cargo_view.retranslate()
        self.preferences_view.retranslate()
        self.wine_runners_view.retranslate()
        self.recipes_view.retranslate()

        if self.tray_icon and self.tray_icon.contextMenu():
            actions = self.tray_icon.contextMenu().actions()
            if len(actions) >= 2:
                actions[0].setText("Show Thatch" if ACTIVE_LANG == "en" else "Mostrar Thatch")
                actions[1].setText("Exit" if ACTIVE_LANG == "en" else "Salir")

        if self.chest_details_view.prefix_name:
            if hasattr(self.sidebar, "btn_chest_details"):
                self.sidebar.btn_chest_details.setText(
                    f"📦  {self.chest_details_view.prefix_name.replace('_', ' ').title()}"
                )
            self._on_chest_selected(self.chest_details_view.prefix_name)

    @Slot(str)
    def _on_toast_requested(self, message: str) -> None:
        self.toast.show_message(message)

    @Slot()
    def _on_runner_downloaded(self) -> None:
        runners = self._get_runners_list()
        self.preferences_view.update_runners_list(runners)
        self.wine_runners_view.update_runners_list(runners)
        self.refresh_data()


if __name__ == "__main__":
    import signal

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("Thatch")
    app.setDesktopFileName("thatch-installer")
    app.setQuitOnLastWindowClosed(False)
    icon_path = Path(__file__).parent / "assets" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    from style import apply_theme

    apply_theme(app)
    gui = ThatchLauncher()
    if not gui.is_installer_mode:
        gui.show()
    sys.exit(app.exec())
