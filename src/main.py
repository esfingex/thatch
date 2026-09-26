#!/usr/bin/env python3
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QSystemTrayIcon,
    QMenu,
    QStackedWidget,
)
from PySide6.QtCore import Slot
from PySide6.QtGui import QIcon, QAction

# Import modular backend components
from database import ThatchDB
from hardware import detect_gpu
from desktop_integration import update_system_context_menu
from i18n import _

# Import modular views package
from views import (
    UnifiedSidebar,
    ChestsView,
    ChestDetailsView,
    MapasView,
    PreferencesView,
    WineRunnersView,
    ToastNotification,
    RecipesView,
)

# Import modular core services
import core

# Import extracted controllers
from controllers import ChestsController, WinetricksController

__version__ = "1.0.1"


# ─── MAIN COORDINATOR WINDOW: THATCHLAUNCHER ──────────────────────────────────


class ThatchLauncher(QMainWindow):
    """
    Main coordinator window linking the layout architecture
    with database, views, and core Wine execution services.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"🏴‍☠️ Thatch - {_('app_title')} v{__version__}")
        self.resize(1000, 680)

        # Initialize databases & hardware probes
        self.db = ThatchDB()
        self.recipes = self.db.load_recipes()
        self.active_gpu = detect_gpu()

        self.process = None
        self.console_dialog = None
        self.tray_icon = None
        self.is_installer_mode = False

        # Controllers own the winetricks machinery and the chest-action handlers.
        self.winetricks_ctrl = WinetricksController(self)
        self.chests_ctrl = ChestsController(self)

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
            show_title = _("main_tray_show")
            quit_title = _("main_tray_exit")

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
        self.chests_view.create_requested.connect(self.chests_ctrl._on_create_chest_requested)
        self.chests_view.chest_selected.connect(self._on_chest_selected)
        self.view_stack.addWidget(self.chests_view)

        # View 1: Chest Details View
        self.chest_details_view = ChestDetailsView(self.active_gpu, self)
        self.chest_details_view.back_requested.connect(
            lambda: self._on_sidebar_view_changed("chests")
        )
        self.chest_details_view.run_requested.connect(self.chests_ctrl._on_chest_run)
        self.chest_details_view.browse_requested.connect(self.chests_ctrl._on_chest_browse)
        self.chest_details_view.terminal_requested.connect(self.chests_ctrl._on_chest_terminal)
        self.chest_details_view.rename_requested.connect(self.chests_ctrl._on_chest_rename)
        self.chest_details_view.delete_requested.connect(self.chests_ctrl._on_chest_delete)
        self.chest_details_view.add_program_requested.connect(self.chests_ctrl._on_chest_add_program)
        self.chest_details_view.run_program_requested.connect(
            self.chests_ctrl._on_chest_run_program
        )
        self.chest_details_view.remove_program_requested.connect(
            self.chests_ctrl._on_chest_remove_program
        )
        self.chest_details_view.remove_link_requested.connect(
            self.chests_ctrl._on_chest_remove_link
        )
        self.chest_details_view.run_installer_requested.connect(self._on_chest_run_installer)
        self.chest_details_view.install_dependency_requested.connect(
            self.winetricks_ctrl._on_chest_install_dependency
        )
        self.chest_details_view.remove_dependency_requested.connect(
            self.winetricks_ctrl._on_chest_remove_dependency
        )
        self.chest_details_view.runner_changed.connect(self.chests_ctrl._on_chest_runner_changed)
        self.chest_details_view.perf_settings_changed.connect(
            self.chests_ctrl._on_chest_perf_settings_changed
        )
        self.chest_details_view.virtual_desktop_changed.connect(
            self.chests_ctrl._on_chest_virtual_desktop_changed
        )
        self.chest_details_view.dpi_scale_changed.connect(
            self.chests_ctrl._on_chest_dpi_scale_changed
        )
        self.chest_details_view.monitor_changed.connect(self.chests_ctrl._on_chest_monitor_changed)
        self.chest_details_view.link_registry_program_requested.connect(
            self.chests_ctrl._on_link_registry_program
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
        self.preferences_view.update_catalog_requested.connect(
            self.winetricks_ctrl._on_update_catalog_requested
        )
        self.preferences_view.cleanup_orphans_requested.connect(
            self.chests_ctrl._on_manual_cleanup_orphans
        )
        self.preferences_view.register_context_menu_requested.connect(
            self.chests_ctrl.register_context_menu
        )
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

    # ─── CONTROLLER DELEGATES (external callers & internals) ──────────────────

    def load_winetricks_catalog(self) -> list[dict]:
        return self.winetricks_ctrl.load_winetricks_catalog()

    def get_installed_verbs(self, prefix_name: str) -> list[str]:
        return self.winetricks_ctrl.get_installed_verbs(prefix_name)

    def _on_chest_add_program(self, prefix_name: str, exe_path_override: str | None = None) -> None:
        self.chests_ctrl._on_chest_add_program(prefix_name, exe_path_override)

    def _on_chest_wizard_finish(
        self, name: str, recipe_id: str, runner_name: str, sandbox_enabled: bool
    ) -> None:
        self.chests_ctrl._on_chest_wizard_finish(name, recipe_id, runner_name, sandbox_enabled)

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


    # ─── CARGO VIEW (MAPAS) SLOTS ─────────────────────────────────────────────

    @Slot(str, str)
    def _on_cargo_install_requested(self, prefix_name: str, recipe_id: str) -> None:
        recipe = self.recipes.get(recipe_id, {})
        verbs = recipe.get("required_verbs", [])

        if not verbs:
            self.toast.show_message(
                _("main_toast_no_verbs", recipe_name=recipe.get("display_name", recipe_id))
            )
            return

        installed = self.get_installed_verbs(prefix_name)
        to_install = [v for v in verbs if v not in installed]

        if not to_install:
            self.toast.show_message(
                _(
                    "main_toast_verbs_installed",
                    recipe_name=recipe.get("display_name", recipe_id),
                    prefix_name=prefix_name,
                )
            )
            return

        self.winetricks_ctrl._queue_winetricks_injections(prefix_name, to_install)

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
                actions[0].setText(_("main_tray_show"))
                actions[1].setText(_("main_tray_exit"))

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
