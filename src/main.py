#!/usr/bin/env python3
import sys
import os
import shutil
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QInputDialog,
    QDialog,
    QTextEdit,
    QSystemTrayIcon,
    QMenu,
    QLineEdit,
    QStackedWidget,
)
from PySide6.QtCore import QProcess, Qt, QProcessEnvironment, QTimer, Slot
from PySide6.QtGui import QIcon, QAction

# Import modular backend components
from database import ThatchDB
from hardware import detect_gpu, compile_performance_env, detect_performance_wrapper
from style import apply_theme

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
from i18n import _, ACTIVE_LANG


__version__ = "1.0.1"


# ─── MODULAR SUPPORT DIALOG: LIVE WINETRICKS CONSOLE ───────────────────────────


class WinetricksConsoleDialog(QDialog):
    """
    Compact dialog showing real-time winetricks installation output console.
    """

    def __init__(self, verb: str, prefix: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Injecting {verb} into {prefix}")
        self.resize(500, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lbl_info = QLabel(f"Installing component: <b>{verb}</b>")
        lbl_info.setStyleSheet("color: #ffffff; font-size: 13px;")
        layout.addWidget(lbl_info)

        self.console = QTextEdit()
        self.console.setObjectName("ConsoleLog")
        self.console.setReadOnly(True)
        layout.addWidget(self.console)

        self.btn_close = QPushButton("Close")
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close)


# ─── MAIN COORDINATOR WINDOW: THATCHLAUNCHER ──────────────────────────────────


class ThatchLauncher(QMainWindow):
    """
    Main coordinator window linking the Figma layout architecture
    with database, hardware hooks, and Wine execution environments.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"🏴‍☠️ Thatch - {_('app_title')} v{__version__}")
        self.resize(1000, 680)

        # Initialize databases
        self.db = ThatchDB()
        self.recipes = self.db.load_recipes()
        self.active_gpu = detect_gpu()

        self.process = None
        self.current_prefix = ""
        self.current_verb = ""
        self.console_dialog = None
        self.tray_icon = None
        self._winetricks_catalog: list[dict] | None = None  # lazy cache

        self.init_tray()
        self.init_ui()
        self.refresh_data()

        # Double click bootstrap handler
        if len(sys.argv) > 1:
            arg_path = Path(sys.argv[1])
            if arg_path.exists() and arg_path.suffix.lower() == ".exe":
                QTimer.singleShot(
                    150, lambda: self._on_zeus_requested_prefilled(str(arg_path))
                )

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
        self.chest_details_view.delete_requested.connect(self._on_chest_delete)
        self.chest_details_view.add_program_requested.connect(
            self._on_chest_add_program
        )
        self.chest_details_view.run_program_requested.connect(
            self._on_chest_run_program
        )
        self.chest_details_view.remove_program_requested.connect(
            self._on_chest_remove_program
        )
        self.chest_details_view.run_installer_requested.connect(
            self._on_chest_run_installer
        )
        self.chest_details_view.install_dependency_requested.connect(
            self._on_chest_install_dependency
        )
        self.chest_details_view.remove_dependency_requested.connect(
            self._on_chest_remove_dependency
        )
        self.chest_details_view.runner_changed.connect(self._on_chest_runner_changed)
        self.chest_details_view.perf_settings_changed.connect(
            self._on_chest_perf_settings_changed
        )
        self.chest_details_view.virtual_desktop_changed.connect(
            self._on_chest_virtual_desktop_changed
        )
        self.chest_details_view.dpi_scale_changed.connect(
            self._on_chest_dpi_scale_changed
        )
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
        self.preferences_view.update_catalog_requested.connect(
            self._on_update_catalog_requested
        )
        self.preferences_view.combo_language.currentIndexChanged.connect(
            self.on_language_changed
        )
        self.view_stack.addWidget(self.preferences_view)

        # View 4: Wine Runners View
        self.wine_runners_view = WineRunnersView(
            self.db, self._get_runners_list(), self
        )
        self.wine_runners_view.runner_downloaded.connect(self._on_runner_downloaded)
        self.wine_runners_view.toast_requested.connect(self._on_toast_requested)
        self.view_stack.addWidget(self.wine_runners_view)

        # View 5: Recipes View
        recipes_dir = Path("config/recipes")
        self.recipes_view = RecipesView(recipes_dir, self)
        self.view_stack.addWidget(self.recipes_view)

        # 3. Toast Notifications Overlay
        self.toast = ToastNotification(self)

    def load_winetricks_catalog(self) -> list[dict]:
        """
        Loads the winetricks catalog of verbs from SQLite cache.
        If cache is empty, returns an empty list and triggers background scan to save to SQLite.
        """
        if self._winetricks_catalog is not None:
            return self._winetricks_catalog

        # 1. Try reading from SQLite cache
        try:
            cached = self.db.get_winetricks_catalog()
            if cached:
                self._winetricks_catalog = cached
                print(
                    f"[WinetricksCatalog] Loaded {len(cached)} verbs instantly from SQLite cache."
                )
                return cached
        except Exception as e:
            print(f"[WinetricksCatalog] Failed to read SQLite cache: {e}")

        # If cache is empty, we do NOT use curated fallbacks anymore.
        self._winetricks_catalog = []

        # 3. Spin background thread to query winetricks, save to SQLite, and keep cache active
        self._trigger_winetricks_catalog_refresh(silent=True)
        return self._winetricks_catalog

    def _trigger_winetricks_catalog_refresh(self, silent: bool = True) -> None:
        """Launches a background daemon thread to scan the full winetricks catalog and persist it in SQLite."""
        import threading

        _enrichment: dict[str, tuple[str, str]] = {
            "dxvk": (
                "DXVK (Vulkan Translation)",
                "High-performance DirectX 9/10/11 to Vulkan translation layer",
            ),
            "dxvk2": (
                "DXVK 2.x (Vulkan Translation)",
                "Latest DXVK with improved DX12 support via VKD3D-Proton",
            ),
            "vkd3d": (
                "VKD3D (DX12 → Vulkan)",
                "DirectX 12 to Vulkan translation layer",
            ),
            "vcrun2015": (
                "Visual C++ 2015 Runtime",
                "Microsoft Visual C++ 2015 standard runtime libraries",
            ),
            "vcrun2017": (
                "Visual C++ 2017 Runtime",
                "C++ runtime files for programs built with VC++ 2017",
            ),
            "vcrun2019": (
                "Visual C++ 2019 Runtime",
                "C++ runtime for modern applications built with MSVC 2019",
            ),
            "vcrun2022": (
                "Visual C++ 2022 Runtime",
                "Latest Microsoft Visual C++ runtime package",
            ),
            "vcrun2013": (
                "Visual C++ 2013 Runtime",
                "Standard libraries for applications compiled with VC++ 2013",
            ),
            "dotnet48": (
                ".NET Framework 4.8",
                "Microsoft .NET Framework 4.8 runtime environment",
            ),
            "dotnet6": (
                ".NET 6 Runtime",
                "Cross-platform .NET 6 runtime for modern Windows apps",
            ),
            "dotnet7": (
                ".NET 7 Runtime",
                "Cross-platform .NET 7 runtime for modern Windows apps",
            ),
            "d3dx9": (
                "DirectX 9 DLLs",
                "Legacy Direct3D 9 runtime files for older software",
            ),
            "d3dcompiler_47": (
                "D3D Shader Compiler 47",
                "Direct3D shader compiler library (d3dcompiler_47.dll)",
            ),
            "physx": (
                "NVIDIA PhysX System",
                "NVIDIA hardware-accelerated physics engine runtime",
            ),
            "msxml6": ("MSXML 6.0 Services", "Microsoft XML parser runtimes and tools"),
            "corefonts": (
                "Microsoft Core Fonts",
                "Standard Windows web fonts (Arial, Times New Roman, Courier)",
            ),
            "tahoma": (
                "Tahoma Font",
                "TrueType font designed primarily for Windows UI elements",
            ),
            "liberation": (
                "Liberation Fonts",
                "Metrically compatible fonts for Arial, Times, Courier",
            ),
            "sandbox": (
                "Sandbox Mode",
                "Disable Desktop/Documents folder mappings to keep your system clean",
            ),
            "sound=alsa": (
                "ALSA Audio Driver",
                "Configures Wine audio system to route through ALSA",
            ),
            "renderer=vulkan": (
                "Vulkan Renderer",
                "Forces Wine to use the modern Vulkan graphics pipeline",
            ),
            "fontsmooth=rgb": (
                "RGB Font Smoothing",
                "Enables subpixel RGB font antialiasing inside Wine applications",
            ),
        }

        def bg_loader():
            import shutil
            import subprocess

            if not shutil.which("winetricks"):
                if not silent:
                    self.toast.show_message(
                        "Error: 'winetricks' is not installed."
                        if ACTIVE_LANG == "en"
                        else "Error: 'winetricks' no está instalado en el sistema."
                    )
                return

            category_commands = [
                ("Libraries", ["winetricks", "dlls", "list"]),
                ("Fonts", ["winetricks", "fonts", "list"]),
                ("Settings", ["winetricks", "settings", "list"]),
            ]

            full_catalog = []
            seen = set()

            for cat_name, cmd in category_commands:
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=20
                    )
                    for line in result.stdout.splitlines():
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split(None, 1)
                        if not parts:
                            continue
                        verb = parts[0].strip()
                        wt_desc = parts[1].strip() if len(parts) > 1 else ""
                        if not verb or verb in seen:
                            continue
                        seen.add(verb)

                        if verb in _enrichment:
                            e_name, e_desc = _enrichment[verb]
                        else:
                            e_name = verb.replace("_", " ").replace("=", ": ").title()
                            e_desc = wt_desc
                        full_catalog.append(
                            {
                                "verb": verb,
                                "name": e_name,
                                "desc": e_desc,
                                "type": cat_name,
                            }
                        )
                except Exception as e:
                    print(f"[WinetricksCatalog BG] Failed to load {cat_name}: {e}")

            if full_catalog:
                try:
                    self.db.save_winetricks_catalog(full_catalog)
                    self._winetricks_catalog = full_catalog
                    print(
                        f"[WinetricksCatalog BG] Successfully cached {len(full_catalog)} verbs to SQLite."
                    )
                    if not silent:
                        self.toast.show_message(
                            _("toast_catalog_updated", count=len(full_catalog))
                        )
                        self.refresh_data()
                except Exception as e:
                    print(
                        f"[WinetricksCatalog BG] Failed to cache catalog to SQLite: {e}"
                    )
            else:
                if not silent:
                    self.toast.show_message(_("toast_catalog_failed"))

        threading.Thread(target=bg_loader, daemon=True).start()

    @Slot()
    def _on_update_catalog_requested(self) -> None:
        """Invoked when the user manually requests a winetricks catalog update in Preferences."""
        self.toast.show_message(_("toast_catalog_updating"))
        self._trigger_winetricks_catalog_refresh(silent=False)

    def _get_runners_list(self) -> list[str]:
        runners_dir = self.db.get_runners_dir()
        if runners_dir.exists():
            return sorted([d.name for d in runners_dir.iterdir() if d.is_dir()])
        return []

    def refresh_data(self) -> None:
        """Reloads active lists across all widgets."""
        prefixes = self.db.list_existing_prefixes()
        games = self.db.list_games()
        runners = self._get_runners_list()

        # Auto-align game recipe IDs with their prefix's primary system container recipe
        updated_db = False
        for prefix_name in prefixes:
            primary_recipe = None
            for gname, ginfo in games.items():
                if ginfo.get(
                    "prefix"
                ) == prefix_name and "Contenedor de Sistema" in ginfo.get("exe", ""):
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
            games = self.db.list_games()  # reload games

        # Populate views
        self.chests_view.populate_chests(
            prefixes, games, self.recipes, self.db.get_prefixes_dir()
        )
        self.cargo_view.populate_maps(prefixes, self.recipes)
        self.preferences_view.update_runners_list(runners)
        self.wine_runners_view.update_runners_list(runners)

        # If detail view is open on a prefix, refresh it
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

    def get_wine_installed_programs(self, prefix_name: str) -> list[dict]:
        """
        Reads Wine WINEPREFIX registry files (system.reg + user.reg) line-by-line to detect
        installed programs. Optimized to prevent memory bloat and CPU spikes on large registry files.
        """
        prefix_path = self.db.get_prefixes_dir() / prefix_name
        drive_c = prefix_path / "drive_c"
        results: list[dict] = []
        seen_ids: set[str] = set()

        def _win_to_linux(win_path: str) -> str:
            if not win_path:
                return ""
            normalized = win_path.replace("\\\\", "\\").replace("\\", "/")
            if normalized.startswith('"') and normalized.endswith('"'):
                normalized = normalized[1:-1]
            import re

            normalized = re.sub(r"^[Cc]:/", "", normalized)
            return str(drive_c / normalized)

        # Skip system/Wine internal components
        skip_patterns = {
            "wine",
            "mono",
            "gecko",
            "microsoft visual c++",
            "windows",
            "directx",
            ".net",
            "vcredist",
        }

        # Parse HKLM (system.reg) and HKCU (user.reg)
        for reg_file in [prefix_path / "system.reg", prefix_path / "user.reg"]:
            if not reg_file.exists():
                continue
            try:
                with open(reg_file, "r", encoding="utf-8", errors="ignore") as f:
                    in_uninstall = False
                    current_app = {}

                    for line in f:
                        line_stripped = line.strip()
                        if not line_stripped:
                            continue

                        # Detect section header
                        if line_stripped.startswith("[") and line_stripped.endswith(
                            "]"
                        ):
                            # Save the previous uninstall app if valid
                            if in_uninstall and current_app.get("name"):
                                app_id = current_app["id"]
                                if app_id not in seen_ids:
                                    display_name = current_app["name"]
                                    if not any(
                                        p in display_name.lower() for p in skip_patterns
                                    ):
                                        seen_ids.add(app_id)
                                        results.append(current_app)

                            current_app = {}
                            in_uninstall = False

                            # Check if HKLM/HKCU Uninstall key
                            header = line_stripped[1:-1].lower()
                            uninstall_prefix = "software\\microsoft\\windows\\currentversion\\uninstall\\"
                            if uninstall_prefix in header:
                                orig_header = line_stripped[1:-1]
                                idx = orig_header.lower().find(uninstall_prefix)
                                app_id = (
                                    orig_header[idx + len(uninstall_prefix) :]
                                    .strip()
                                    .strip("\"'")
                                )
                                if app_id:
                                    in_uninstall = True
                                    current_app = {
                                        "id": app_id,
                                        "name": "",
                                        "version": "",
                                        "publisher": "",
                                        "install_location": "",
                                        "install_location_win": "",
                                        "uninstall_string": "",
                                        "display_icon_win": "",
                                    }
                            continue

                        if in_uninstall:
                            if "=" in line_stripped:
                                parts = line_stripped.split("=", 1)
                                key = parts[0].strip().strip('"').lower()
                                val = parts[1].strip()

                                if val.startswith('"') and val.endswith('"'):
                                    val = val[1:-1].replace("\\\\", "\\")

                                if key == "displayname":
                                    current_app["name"] = val
                                elif key == "displayversion":
                                    current_app["version"] = val
                                elif key == "publisher":
                                    current_app["publisher"] = val
                                elif key == "installlocation":
                                    current_app["install_location_win"] = val
                                    current_app["install_location"] = _win_to_linux(val)
                                elif key == "uninstallstring":
                                    current_app["uninstall_string"] = val
                                elif key == "displayicon":
                                    current_app["display_icon_win"] = val

                    # Check the last parsed app in the file
                    if in_uninstall and current_app.get("name"):
                        app_id = current_app["id"]
                        if app_id not in seen_ids:
                            display_name = current_app["name"]
                            if not any(
                                p in display_name.lower() for p in skip_patterns
                            ):
                                seen_ids.add(app_id)
                                results.append(current_app)
            except Exception as e:
                print(f"Error parsing registry file {reg_file.name}: {e}")

        return results

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

    def get_wine_env(
        self, prefix_name: str, recipe_id: str, runner_override: str | None = None
    ) -> tuple[dict[str, str], Path | None]:
        recipe = self.recipes.get(recipe_id, {})
        recipe_env = recipe.get("performance_env", {})

        env = compile_performance_env(self.active_gpu, recipe_env)
        env["WINEPREFIX"] = str(self.db.get_prefixes_dir() / prefix_name)
        env["WINETRICKS_CACHE"] = str(self.db.get_winetricks_cache_dir())
        env["WINETRICKS_DOWNLOADER"] = "curl"

        selected_runner = (
            runner_override
            if runner_override
            else (
                self.db.data["global_config"].get("default_runner", "")
                or "Wine del Sistema (/usr/bin/wine)"
            )
        )
        runners_dir = self.db.get_runners_dir()
        runner_path = runners_dir / selected_runner

        if runner_path.exists():
            bin_dir = (
                runner_path / "files" / "bin"
                if (runner_path / "files").exists()
                else runner_path / "bin"
            )
            lib_dir = (
                runner_path / "files" / "lib"
                if (runner_path / "files").exists()
                else runner_path / "lib"
            )
            lib64_dir = (
                runner_path / "files" / "lib64"
                if (runner_path / "files").exists()
                else runner_path / "lib64"
            )

            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            env["LD_LIBRARY_PATH"] = (
                f"{lib_dir}:{lib64_dir}:{env.get('LD_LIBRARY_PATH', '')}"
            )
            return env, runner_path

        return env, None

    def _get_pe_arch(self, exe_path: str | Path) -> str:
        """Reads the PE header of an executable to determine its architecture.
        Returns 'x64' for AMD64/ARM64 binaries, 'x86' for 32-bit."""
        try:
            with open(exe_path, "rb") as f:
                f.seek(0x3C)
                pe_offset = int.from_bytes(f.read(4), "little")
                f.seek(pe_offset + 4)  # Skip "PE\0\0" signature
                machine = int.from_bytes(f.read(2), "little")
                # 0x8664 = AMD64 (x86_64), 0xAA64 = ARM64
                if machine in (0x8664, 0xAA64):
                    return "x64"
        except Exception:
            pass
        return "x86"

    def _get_wine_cmd(self, runner_path, exe_path: str | Path | None = None) -> str:
        """Returns the correct wine or wine64 binary for the runner.
        Auto-detects PE32+ (x64) executables and upgrades to wine64 automatically."""
        if runner_path and runner_path.exists():
            bin_dir = (
                runner_path / "files" / "bin"
                if (runner_path / "files").exists()
                else runner_path / "bin"
            )
        else:
            bin_dir = None

        is_x64 = (
            self._get_pe_arch(exe_path) == "x64"
            if exe_path
            else False
        )

        wine_bin = "wine64" if is_x64 else "wine"

        if bin_dir:
            candidate = bin_dir / wine_bin
            if candidate.exists():
                return str(candidate)
            # Fallback: try the other variant
            fallback = bin_dir / ("wine" if is_x64 else "wine64")
            if fallback.exists():
                return str(fallback)
            return str(bin_dir / "wine")

        # System wine fallback
        return wine_bin

    # ─── SIDEBAR EVENT HANDLERS ────────────────────────────────────────────────

    @Slot(str)
    def _on_sidebar_view_changed(self, view_name: str) -> None:
        self.sidebar.set_active_view(view_name)
        self.refresh_data()

        if view_name == "chests":
            self.view_stack.setCurrentIndex(0)
        elif view_name == "cargo":
            self.view_stack.setCurrentIndex(2)
        elif view_name == "runners":
            self.view_stack.setCurrentIndex(4)
        elif view_name == "recipes":
            self.view_stack.setCurrentIndex(5)
        elif view_name == "preferences":
            self.view_stack.setCurrentIndex(3)

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

        # Save a dummy placeholder game or write associated metadata
        # We save it as a custom game representation so that it is captured in the database
        self.db.add_game(
            name=name.replace("_", " ").title(),
            exe="Contenedor de Sistema",
            runner=runner_name,
            prefix=name,
            recipe_id=recipe_id,
        )

        # Explicitly update sandbox value in cache and save
        games = self.db.list_games()
        chest_placeholder = name.replace("_", " ").title()
        if chest_placeholder in games:
            games[chest_placeholder]["sandbox"] = sandbox_enabled
            self.db.save()

        # Build Wine environment and find the core wine command
        env, runner_path = self.get_wine_env(name, recipe_id, runner_name)

        wine_exe = self._get_wine_cmd(runner_path)

        self.toast.show_message(
            f"Creando e inicializando contenedor de Wine para '{name}'..."
        )

        # Open visual console dialog for real-time creation logs! (Absolut User Transparency)
        self.console_dialog = WinetricksConsoleDialog(
            "wineboot (Inicialización de Sistema)", name, self
        )
        self.console_dialog.setWindowTitle(f"Creating Chest: {name}")
        self.console_dialog.console.append(
            f":: [THATCH] Bootstrapping isolated WINEPREFIX in {prefix_path}..."
        )
        self.console_dialog.console.append(
            f":: [THATCH] Running wineboot -u command via '{wine_exe}'..."
        )
        self.console_dialog.show()

        # Spawn wine wineboot -u asynchronously to populate drive_c and registries!
        # This is compatible with all Wine versions and modern Proton 10/WOW64 builds which don't ship a standalone 'wineboot' binary.
        self.process = QProcess()
        q_env = QProcessEnvironment()
        for k, v in env.items():
            # Skip display to force wineboot to run completely headless without window deadlocks
            if k == "DISPLAY":
                continue
            q_env.insert(k, v)

        # Explicit headless/silent indicators for modern Wine runners
        q_env.insert("DISPLAY", "")
        q_env.insert("WINEHEADLESS", "1")

        # Disable ESYNC/FSYNC for wineboot to prevent futex locks / hang deadlocks in sandboxed and clean prefixes
        q_env.insert("WINEESYNC", "0")
        q_env.insert("WINEFSYNC", "0")
        q_env.insert("WINEMFSYNC", "0")

        # Suppress noisy debug logs that can fill QProcess buffers and cause pipe write deadlocks
        q_env.insert("WINEDEBUG", "-all")

        # Disable Wine Mono and Wine Gecko prompts to prevent silent hang deadlocks in headless wineboot
        if "WINEDLLOVERRIDES" in env:
            q_env.insert(
                "WINEDLLOVERRIDES", env["WINEDLLOVERRIDES"] + ";mscoree,mshtml=d"
            )
        else:
            q_env.insert("WINEDLLOVERRIDES", "mscoree,mshtml=d")

        # Force 64-bit prefix when recipe explicitly declares it or runner supports it
        recipe_obj = self.recipes.get(recipe_id, {})
        recipe_perf = recipe_obj.get("performance_env", {})
        if recipe_perf.get("WINEARCH") == "win64" or recipe_perf.get("WINEARCH64"):
            q_env.insert("WINEARCH", "win64")
            self.console_dialog.console.append(
                ":: [THATCH] Recipe requests 64-bit prefix → WINEARCH=win64"
            )

        self.process.setProcessEnvironment(q_env)

        self.process.readyReadStandardOutput.connect(self._on_winetricks_stdout)
        self.process.readyReadStandardError.connect(self._on_winetricks_stderr)
        self.process.finished.connect(
            lambda exit_code, exit_status, n=name: self._on_chest_init_finished(
                exit_code, n
            )
        )
        self.process.errorOccurred.connect(
            lambda err, n=name: self._on_chest_init_error(err, n)
        )
        self.process.start(wine_exe, ["wineboot", "-u"])

        self.refresh_data()

    def _on_chest_init_error(self, error: QProcess.ProcessError, name: str) -> None:
        error_msg = f"\n:: [ERROR] Failed to execute wineboot command! QProcess error code: {error}\n"
        print(error_msg)
        if self.console_dialog:
            self.console_dialog.console.append(error_msg)
            self.console_dialog.btn_close.setEnabled(True)
        self.toast.show_message(f"Error crítico al iniciar Wine: {error}")

    def _on_chest_init_finished(self, exit_code: int, name: str) -> None:
        self.refresh_data()

        if exit_code == 0:
            # Close the initialization console dialog only if creation succeeded
            if self.console_dialog:
                self.console_dialog.close()
                self.console_dialog = None
            self.toast.show_message(
                f"¡Contenedor '{name}' inicializado! Buscando dependencias..."
            )

            # Auto-install winetricks dependencies required by the recipe!
            recipe_id = self._get_chest_recipe_id(name)
            recipe = self.recipes.get(recipe_id, {})
            required_verbs = recipe.get("required_verbs", [])

            if required_verbs:
                self.toast.show_message(
                    f"Inyectando {len(required_verbs)} componentes de la receta automáticamente..."
                )
                self.winetricks_queue_prefix = name
                self.winetricks_queue = list(required_verbs)
                self._process_next_winetricks_queue()
            else:
                self.toast.show_message(f"¡Contenedor '{name}' inicializado y listo!")
        else:
            # Keep console dialog open to show error outputs to the user, and unlock Close button
            if self.console_dialog:
                self.console_dialog.console.append(
                    f"\n:: [ERROR] wineboot failed with exit code: {exit_code}"
                )
                self.console_dialog.console.append(
                    ":: [THATCH] Check console output or verify runner/libraries compatibility."
                )
                self.console_dialog.btn_close.setEnabled(True)
            self.toast.show_message(
                f"Contenedor '{name}' falló al crearse (código {exit_code})."
            )

    @Slot(str)
    def _on_chest_selected(self, prefix_name: str) -> None:
        """Navigates to the details tab stack of a single prefix chest."""
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
        self.view_stack.setCurrentIndex(1)

    # ─── CHEST DETAILS VIEW ACTIONS ────────────────────────────────────────────

    @Slot(str)
    def _on_chest_run(self, prefix_name: str) -> None:
        """Launches the default game executable associated with the prefix, or drive_c folder."""
        games = self.db.list_games()
        target_game_name = None
        for gname, ginfo in games.items():
            if ginfo.get(
                "prefix"
            ) == prefix_name and "Contenedor de Sistema" not in ginfo.get("exe", ""):
                target_game_name = gname
                break

        if target_game_name:
            self._on_chest_run_program(prefix_name, target_game_name)
        else:
            # Just open drive_c
            self._on_chest_browse(prefix_name)

    @Slot(str)
    def _on_chest_browse(self, prefix_name: str) -> None:
        prefix_path = self.db.get_prefixes_dir() / prefix_name / "drive_c"
        prefix_path.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(prefix_path)])
        self.toast.show_message("Abriendo explorador de archivos...")

    @Slot(str)
    def _on_chest_terminal(self, prefix_name: str) -> None:
        """Power-user hook: spawns an active bash terminal inside the WINEPREFIX env context!"""
        env, _ = self.get_wine_env(prefix_name, "default_gaming")
        prefix_path = self.db.get_prefixes_dir() / prefix_name

        # Load terminal choice from DB preference, fallback to scan
        terminal = self.db.data["global_config"].get("default_terminal", "")
        if not terminal:
            terminals = [
                "gnome-terminal",
                "konsole",
                "alacritty",
                "kitty",
                "xfce4-terminal",
                "xterm",
                "tilix",
            ]
            for t in terminals:
                if shutil.which(t):
                    terminal = t
                    break

        if not terminal or not shutil.which(terminal):
            QMessageBox.critical(
                self,
                "No Terminal Emulator",
                "No se detectó el emulador de terminal configurado.",
            )
            return

        # Spawn terminal with custom variables
        cmd = []
        if terminal == "gnome-terminal":
            cmd = [
                "gnome-terminal",
                "--",
                "bash",
                "-c",
                f"export WINEPREFIX='{env['WINEPREFIX']}'; export PATH='{env['PATH']}'; export LD_LIBRARY_PATH='{env.get('LD_LIBRARY_PATH', '')}'; cd '{prefix_path}'; exec bash",
            ]
        elif terminal == "konsole":
            cmd = [
                "konsole",
                "-e",
                "bash",
                "-c",
                f"export WINEPREFIX='{env['WINEPREFIX']}'; export PATH='{env['PATH']}'; export LD_LIBRARY_PATH='{env.get('LD_LIBRARY_PATH', '')}'; cd '{prefix_path}'; exec bash",
            ]
        elif terminal in ["alacritty", "kitty"]:
            cmd = [
                terminal,
                "-e",
                "bash",
                "-c",
                f"export WINEPREFIX='{env['WINEPREFIX']}'; export PATH='{env['PATH']}'; export LD_LIBRARY_PATH='{env.get('LD_LIBRARY_PATH', '')}'; cd '{prefix_path}'; exec bash",
            ]
        else:
            cmd = [
                terminal,
                "-e",
                f"WINEPREFIX={env['WINEPREFIX']} PATH={env['PATH']} LD_LIBRARY_PATH={env.get('LD_LIBRARY_PATH', '')} bash",
            ]

        try:
            subprocess.Popen(cmd)
            self.toast.show_message("Consola de terminal iniciada.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al abrir la terminal: {e}")

    @Slot(str)
    def _on_chest_delete(self, prefix_name: str) -> None:
        res = QMessageBox.question(
            self,
            "Borrar Contenedor",
            f"¿Seguro que deseas borrar permanentemente el Chest '{prefix_name}'?\n"
            "Esto eliminará su carpeta WINEPREFIX y todos los programas asociados.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if res == QMessageBox.Yes:
            prefix_path = self.db.get_prefixes_dir() / prefix_name

            # Remove associated games and their launchers from DB & system
            games = list(self.db.list_games().keys())
            for gname in games:
                ginfo = self.db.get_game(gname)
                if ginfo and ginfo.get("prefix") == prefix_name:
                    self.remove_launcher(prefix_name, gname)
                    self.db.remove_game(gname)

            shutil.rmtree(prefix_path, ignore_errors=True)
            self._on_sidebar_view_changed("chests")
            self.toast.show_message(
                f"Chest '{prefix_name}' y todos sus lanzadores eliminados."
            )

    def _get_chest_recipe_id(self, prefix_name: str) -> str:
        """Finds the primary recipe ID associated with the system container for a given prefix."""
        for gname, ginfo in self.db.list_games().items():
            if ginfo.get(
                "prefix"
            ) == prefix_name and "Contenedor de Sistema" in ginfo.get("exe", ""):
                return ginfo.get("recipe_id", "default_gaming")
        return "default_gaming"

    @Slot(str)
    def _on_chest_add_program(
        self, prefix_name: str, exe_path_override: str | None = None
    ) -> None:
        """Prompts user to select an .exe file and add it as program list item."""
        if exe_path_override:
            path = exe_path_override
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Executable .exe", "", "Executables (*.exe)"
            )
        if not path:
            return

        exe_path = Path(path)
        game_name = exe_path.parent.name

        name, ok = QInputDialog.getText(
            self,
            "Registrar Programa",
            "Nombre del programa para registrar en la biblioteca:",
            QLineEdit.Normal,
            game_name,
        )
        if ok and name.strip():
            recipe_id = self._get_chest_recipe_id(prefix_name)
            self.db.add_game(
                name=name.strip(),
                exe=str(exe_path),
                runner=self.db.data["global_config"].get("default_runner")
                or "Wine del Sistema (/usr/bin/wine)",
                prefix=prefix_name,
                recipe_id=recipe_id,
            )
            icon_path = self._extract_exe_icon(prefix_name, exe_path, name.strip())
            self.generate_launcher(prefix_name, name.strip(), icon_path)
            self.refresh_data()
            self.toast.show_message(
                f"¡Programa '{name.strip()}' registrado y lanzador directo de Wine creado!"
            )

    def _get_desktop_paths(self) -> list[Path]:
        """Detects all possible system desktop directory locations utilizing XDG specifications and localizations."""
        paths = [Path.home() / "Desktop", Path.home() / "Escritorio"]
        xdg_config = Path.home() / ".config" / "user-dirs.dirs"
        if xdg_config.exists():
            try:
                with open(xdg_config, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("XDG_DESKTOP_DIR="):
                            raw_val = line.split("=")[1].strip().strip('"')
                            raw_val = raw_val.replace("$HOME", str(Path.home()))
                            p = Path(raw_val)
                            if p.exists() and p not in paths:
                                paths.append(p)
            except Exception:
                pass
        return [p for p in paths if p.exists()]

    def generate_launcher(
        self, prefix_name: str, game_name: str, icon_path: Path | None = None
    ) -> None:
        """Generates static independent launcher script (.sh) and desk shortcut (.desktop) for the game."""
        game_info = self.db.get_game(game_name)
        if not game_info:
            return

        prefix_path = self.db.get_prefixes_dir() / prefix_name
        launchers_dir = prefix_path / "launchers"
        launchers_dir.mkdir(parents=True, exist_ok=True)

        # Clean game name for filename
        clean_name = (
            game_name.lower().replace(" ", "_").replace("/", "_").replace(".", "_")
        )
        sh_path = launchers_dir / f"{clean_name}.sh"

        # Compile environment
        env, runner_path = self.get_wine_env(
            prefix_name,
            game_info.get("recipe_id", "default_gaming"),
            game_info.get("runner"),
        )

        exe_for_arch = Path(game_info.get("exe", "")) if game_info else None
        wine_cmd = self._get_wine_cmd(runner_path, exe_for_arch)

        # Target Monitor setting
        target_monitor = game_info.get("target_monitor", "default")

        # Write .sh script
        try:
            with open(sh_path, "w", encoding="utf-8") as f:
                f.write("#!/bin/bash\n")
                f.write(f"# Lanzador directo de {game_name} generado por Thatch\n\n")

                # Check for screen override
                if target_monitor != "default":
                    f.write(
                        "# Cambiar monitor primario temporalmente para forzar Wine a iniciar ahí\n"
                    )
                    f.write(
                        'OLD_PRIMARY=$(xrandr --query | grep " primary" | cut -d" " -f1)\n'
                    )
                    f.write(f'TARGET_MONITOR="{target_monitor}"\n')
                    f.write(
                        'if [ -n "$TARGET_MONITOR" ] && [ "$TARGET_MONITOR" != "$OLD_PRIMARY" ]; then\n'
                    )
                    f.write('    xrandr --output "$TARGET_MONITOR" --primary\n')
                    f.write("    # Restaurar monitor primario original al salir\n")
                    f.write(
                        '    trap "xrandr --output $OLD_PRIMARY --primary" EXIT INT TERM\n'
                    )
                    f.write("fi\n\n")

                # Clean & Minimalist System PATH (Avoid bringing local Perl, shell, or temporary bloat)
                clean_sys_path = "/usr/local/bin:/usr/bin:/bin"
                runner_bin = ""

                if runner_path and runner_path.exists():
                    bin_dir = (
                        runner_path / "files" / "bin"
                        if (runner_path / "files").exists()
                        else runner_path / "bin"
                    )
                    runner_bin = f"{bin_dir}:"

                f.write(f'export WINEPREFIX="{env["WINEPREFIX"]}"\n')
                f.write(f'export PATH="{runner_bin}{clean_sys_path}"\n')

                if "LD_LIBRARY_PATH" in env:
                    # Clean up LD_LIBRARY_PATH to only point to runner libraries
                    f.write(f'export LD_LIBRARY_PATH="{env["LD_LIBRARY_PATH"]}"\n')
                f.write(f'export WINETRICKS_CACHE="{env["WINETRICKS_CACHE"]}"\n')

                # Performance settings
                recipe = self.recipes.get(
                    game_info.get("recipe_id", "default_gaming"), {}
                )
                perf_env = recipe.get("performance_env", {})
                for k, v in perf_env.items():
                    f.write(f'export {k}="{v}"\n')

                # Sandbox Isolation Hook (Zeus-Engine Isolated Laboratory)
                sandbox_enabled = bool(game_info.get("sandbox", False))
                if sandbox_enabled:
                    f.write(
                        "\n# Zeus Sandbox Isolation: Restrict disk and user folders access\n"
                    )
                    f.write('if [ -d "$WINEPREFIX/dosdevices" ]; then\n')
                    f.write("    # Disable host root directory mapping (Drive Z:)\n")
                    f.write('    rm -f "$WINEPREFIX/dosdevices/z:"\n')
                    f.write("    \n")
                    f.write(
                        "    # Restrict Wine default documents folders from pointing to your actual Linux home\n"
                    )
                    f.write('    user_dir="$WINEPREFIX/drive_c/users/steamuser"\n')
                    f.write('    if [ -d "$user_dir" ]; then\n')
                    f.write(
                        '        for folder in "Desktop" "Documents" "Downloads" "Music" "Pictures" "Videos"; do\n'
                    )
                    f.write('            if [ -L "$user_dir/$folder" ]; then\n')
                    f.write('                rm -f "$user_dir/$folder"\n')
                    f.write('                mkdir -p "$user_dir/$folder"\n')
                    f.write("            fi\n")
                    f.write("        done\n")
                    f.write("    fi\n")
                    f.write("fi\n")

                # Setup Working Directory (CD to game directory, critical for GOG Games resources)
                exe_file = Path(game_info["exe"])
                game_dir = exe_file.parent
                relative_exe = exe_file.name

                # Special GOG Games check: If the executable is inside x64/ or Bin64/ subfolder,
                # we must change the working directory (cwd) to the parent root folder where GOG resources are!
                if (
                    game_dir.name.lower() in ["x64", "bin64", "bin", "win64", "x86"]
                    and game_dir.parent.name.lower() != "drive_c"
                ):
                    game_dir = game_dir.parent
                    relative_exe = f"{exe_file.parent.name}/{exe_file.name}"

                f.write(
                    f'\n# Entrar al directorio de trabajo del juego\ncd "{game_dir}"\n\n'
                )

                f.write("# Ejecutar directo con Wine\n")
                wrappers = detect_performance_wrapper()
                wrapper_str = " ".join(wrappers) + " " if wrappers else ""

                # Check virtual desktop for this game
                vd_enabled = bool(game_info.get("virtual_desktop", False))
                vd_res = game_info.get("virtual_desktop_res", "1920x1080")
                if vd_enabled:
                    f.write(
                        f'{wrapper_str}"{wine_cmd}" explorer /desktop=Thatch,{vd_res} "{relative_exe}" "$@"\n'
                    )
                else:
                    f.write(f'{wrapper_str}"{wine_cmd}" "{relative_exe}" "$@"\n')

            # Make executable
            sh_path.chmod(0o755)

            # Determine icon: prefer extracted icon, then fall back to themed wine icon
            icon_str = str(icon_path) if (icon_path and icon_path.exists()) else "wine"

            # Create desktop content
            desktop_content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={game_name} ({prefix_name.replace('_', ' ').title()})\n"
                f"Comment=Ejecutar {game_name} con Wine directo vía Thatch\n"
                f'Exec="{sh_path}"\n'
                f"Icon={icon_str}\n"
                "Categories=Game;Utility;\n"
                "Terminal=false\n"
                "StartupNotify=true\n"
            )

            # 1. Create .desktop file under application menu
            desktop_dir = Path.home() / ".local" / "share" / "applications"
            desktop_dir.mkdir(parents=True, exist_ok=True)
            desktop_path = desktop_dir / f"thatch-{prefix_name}-{clean_name}.desktop"

            with open(desktop_path, "w", encoding="utf-8") as f:
                f.write(desktop_content)

            # 2. Create duplicate .desktop file on all detected user Desktop directories
            for desk_p in self._get_desktop_paths():
                target_desk_shortcut = (
                    desk_p / f"thatch-{prefix_name}-{clean_name}.desktop"
                )
                try:
                    with open(target_desk_shortcut, "w", encoding="utf-8") as f:
                        f.write(desktop_content)
                    target_desk_shortcut.chmod(0o755)
                except Exception as desk_err:
                    print(
                        f"[Desktop Shortcut Error] Failed to write to {desk_p.name}: {desk_err}"
                    )

        except Exception as e:
            print(f"[Launcher Error] Failed to generate launchers: {e}")

    def _extract_exe_icon(
        self, prefix_name: str, exe_path: Path, game_name: str
    ) -> Path | None:
        """
        Tries to extract the icon from a Windows .exe using icoextract or wrestool (icoutils).
        Saves the PNG to ~/.local/share/icons/thatch/<prefix>/<clean_name>.png.
        Returns the Path if successful, else None.
        """
        clean_name = (
            game_name.lower().replace(" ", "_").replace("/", "_").replace(".", "_")
        )
        icons_dir = Path.home() / ".local" / "share" / "icons" / "thatch" / prefix_name
        icons_dir.mkdir(parents=True, exist_ok=True)
        out_png = icons_dir / f"{clean_name}.png"

        # Method 1: icoextract (modern, Python-based)
        if shutil.which("icoextract"):
            try:
                result = subprocess.run(
                    ["icoextract", str(exe_path), str(out_png)],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0 and out_png.exists():
                    return out_png
            except Exception:
                pass

        # Method 2: wrestool + icotool (icoutils package)
        if shutil.which("wrestool") and shutil.which("icotool"):
            try:
                ico_path = icons_dir / f"{clean_name}.ico"
                wrestool_result = subprocess.run(
                    ["wrestool", "-x", "-t", "14", "-o", str(ico_path), str(exe_path)],
                    capture_output=True,
                    timeout=10,
                )
                if wrestool_result.returncode == 0 and ico_path.exists():
                    subprocess.run(
                        ["icotool", "-x", "-o", str(icons_dir), str(ico_path)],
                        capture_output=True,
                        timeout=10,
                    )
                    # icotool creates files like name_32x32.png - find the largest one
                    pngs = sorted(
                        icons_dir.glob(f"{clean_name}*.png"),
                        key=lambda p: p.stat().st_size,
                        reverse=True,
                    )
                    if pngs:
                        pngs[0].rename(out_png)
                        ico_path.unlink(missing_ok=True)
                        return out_png
            except Exception:
                pass

        return None

    def remove_launcher(self, prefix_name: str, game_name: str) -> None:
        """Removes the launcher script (.sh) and desk shortcut (.desktop) cleanly from the system."""
        clean_name = (
            game_name.lower().replace(" ", "_").replace("/", "_").replace(".", "_")
        )

        # 1. Delete menu shortcut
        desktop_path = (
            Path.home()
            / ".local"
            / "share"
            / "applications"
            / f"thatch-{prefix_name}-{clean_name}.desktop"
        )
        if desktop_path.exists():
            try:
                desktop_path.unlink()
            except Exception as e:
                print(f"[Launcher Cleanup] Failed to remove desktop file: {e}")

        # 2. Delete all Desktop shortcuts
        for desk_p in self._get_desktop_paths():
            target_desk_shortcut = desk_p / f"thatch-{prefix_name}-{clean_name}.desktop"
            if target_desk_shortcut.exists():
                try:
                    target_desk_shortcut.unlink()
                except Exception as e:
                    print(
                        f"[Launcher Cleanup] Failed to remove Desktop shortcut from {desk_p.name}: {e}"
                    )

        # 3. Delete sh launcher
        prefix_path = self.db.get_prefixes_dir() / prefix_name
        sh_path = prefix_path / "launchers" / f"{clean_name}.sh"
        if sh_path.exists():
            try:
                sh_path.unlink()
            except Exception as e:
                print(f"[Launcher Cleanup] Failed to remove sh file: {e}")

    @Slot(str, str)
    def _on_chest_remove_program(self, prefix_name: str, game_name: str) -> None:
        """Runs the Windows uninstaller for the program, then cleans up Thatch launchers."""
        # Look up uninstall string from Wine registry
        registry_programs = self.get_wine_installed_programs(prefix_name)
        reg_entry = next(
            (r for r in registry_programs if r["name"].lower() == game_name.lower()),
            None,
        )
        uninstall_str = reg_entry.get("uninstall_string", "") if reg_entry else ""

        if uninstall_str:
            confirm = QMessageBox.question(
                self,
                "Desinstalar Programa",
                f"¿Deseas desinstalar '{game_name}'?\n"
                "Se ejecutará el desinstalador de Windows y se eliminarán los accesos directos.",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return

            # Run the Windows uninstaller via Wine
            game_info = self.db.get_game(game_name)
            recipe_id = (
                game_info.get("recipe_id", "default_gaming")
                if game_info
                else "default_gaming"
            )
            env, runner_path = self.get_wine_env(
                prefix_name, recipe_id, game_info.get("runner") if game_info else None
            )

            wine_cmd = self._get_wine_cmd(runner_path)

            # The uninstall string may contain quotes and arguments
            import shlex

            try:
                # Parse it as a command line with possible arguments
                parts = shlex.split(uninstall_str.replace("\\", "/"))
                uninstaller_exe = parts[0] if parts else uninstall_str
                extra_args = parts[1:] if len(parts) > 1 else []
                cmd = [wine_cmd, uninstaller_exe] + extra_args
                subprocess.Popen(cmd, env=env, preexec_fn=os.setpgrp)
                self.toast.show_message(f"Ejecutando desinstalador de '{game_name}'...")
            except Exception as e:
                self.toast.show_message(f"Error al ejecutar desinstalador: {e}")
        else:
            # No registry entry — just unlink from Thatch
            confirm = QMessageBox.question(
                self,
                "Desvincular Programa",
                f"¿Deseas desvincular '{game_name}' de la biblioteca?\n"
                "No se encontró desinstalador de Windows. Solo se eliminarán los accesos directos.",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return

        # In both cases: remove from Thatch DB and clean up launchers
        self.remove_launcher(prefix_name, game_name)
        self.db.remove_game(game_name)
        self.refresh_data()
        self.toast.show_message(
            f"¡Programa '{game_name}' desinstalado y lanzadores eliminados!"
        )

    def win_to_linux_path(self, prefix_name: str, win_path: str) -> Path | None:
        """Converts a Windows C:\\ path to the Linux equivalent inside drive_c."""
        if not win_path:
            return None
        import re

        # Remove comma index suffix (e.g. C:\\path\\to\\exe.exe,0 or C:\\path\\to\\exe.exe,-151)
        win_path = re.sub(r",-?\d+$", "", win_path.strip().strip('"'))
        normalized = win_path.replace("\\\\", "\\").replace("\\", "/")
        normalized = re.sub(r"^[Cc]:/", "", normalized)

        prefix_path = self.db.get_prefixes_dir() / prefix_name
        drive_c = prefix_path / "drive_c"
        return drive_c / normalized

    def detect_game_exe(self, prefix_name: str, reg_entry: dict) -> Path | None:
        """
        Attempts to automatically locate the main game executable for a registry-detected program.
        """
        import re

        # 1. Try DisplayIcon
        display_icon = reg_entry.get("display_icon_win", "")
        if display_icon:
            # Strip quotes and remove icon resource index (e.g. ,0)
            cleaned = re.sub(r",-?\d+$", "", display_icon.strip().strip('"'))
            if cleaned.lower().endswith(".exe"):
                exe_path = self.win_to_linux_path(prefix_name, cleaned)
                if exe_path and exe_path.exists() and exe_path.is_file():
                    return exe_path

        # 2. Try InstallLocation
        install_location = reg_entry.get("install_location", "")
        if install_location:
            loc_path = Path(install_location)
            if loc_path.exists() and loc_path.is_dir():
                # Scan for .exe files recursively (up to 3 levels)
                exe_files = []
                for root, dirs, files in os.walk(loc_path):
                    # Limit depth to 3 levels to avoid deep scanning subdirs of dependencies
                    depth = len(Path(root).relative_to(loc_path).parts)
                    if depth > 3:
                        dirs.clear()  # don't recurse deeper
                        continue
                    for f in files:
                        if f.lower().endswith(".exe"):
                            exe_files.append(Path(root) / f)

                # Filter out uninstallers and other noise
                blacklist = [
                    "unins",
                    "uninstall",
                    "setup",
                    "install",
                    "crash",
                    "unitycrashhandler",
                    "vc_redist",
                    "vcredist",
                    "dxwebsetup",
                    "touchup",
                    "repair",
                    "config",
                    "launcher",
                ]
                filtered_exes = []
                for p in exe_files:
                    name_lower = p.name.lower()
                    if any(b in name_lower for b in blacklist):
                        continue
                    filtered_exes.append(p)

                if len(filtered_exes) == 1:
                    return filtered_exes[0]
                elif len(filtered_exes) > 1:
                    # Try to match name of the game (stem or folder name)
                    game_name = reg_entry.get("name", "").lower()
                    for p in filtered_exes:
                        if p.stem.lower() in game_name or game_name in p.stem.lower():
                            return p
                    # Fallback: return the largest exe file (since the main game is usually largest)
                    try:
                        filtered_exes.sort(key=lambda x: x.stat().st_size, reverse=True)
                        return filtered_exes[0]
                    except Exception:
                        pass

        return None

    @Slot(str, str, str)
    def _on_link_registry_program(
        self, prefix_name: str, reg_id: str, install_location: str
    ) -> None:
        """Handles linking a registry-detected program to its .exe to create a launcher."""
        # Find the registry entry to get the display name
        registry_programs = self.get_wine_installed_programs(prefix_name)
        reg_entry = next((r for r in registry_programs if r["id"] == reg_id), None)
        if not reg_entry:
            return

        suggested_name = reg_entry["name"]

        # Try automatic detection first!
        detected_exe = self.detect_game_exe(prefix_name, reg_entry)
        path = ""
        if detected_exe:
            confirm = QMessageBox.question(
                self,
                "Vincular Programa",
                f"Hemos detectado automáticamente el ejecutable del juego:\n\n"
                f"Nombre: {suggested_name}\n"
                f"Ejecutable: {detected_exe.name}\n\n"
                f"¿Deseas vincular este programa automáticamente?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm == QMessageBox.Yes:
                path = str(detected_exe)

        if not path:
            # Fall back to manual file selection
            start_dir = (
                install_location
                if (install_location and Path(install_location).exists())
                else ""
            )
            if not start_dir:
                start_dir = str(self.db.get_prefixes_dir() / prefix_name / "drive_c")

            path, _ = QFileDialog.getOpenFileName(
                self,
                f"Seleccionar ejecutable de ‘{suggested_name}’",
                start_dir,
                "Executables (*.exe)",
            )

        if not path:
            return

        name, ok = QInputDialog.getText(
            self,
            "Confirmar nombre",
            "Nombre del juego en la biblioteca:",
            QLineEdit.Normal,
            suggested_name,
        )
        if not (ok and name.strip()):
            return

        exe_path = Path(path)
        self.db.add_game(
            name=name.strip(),
            exe=str(exe_path),
            runner=self.db.data["global_config"].get("default_runner")
            or "Wine del Sistema (/usr/bin/wine)",
            prefix=prefix_name,
            recipe_id="default_gaming",
        )
        icon_path = self._extract_exe_icon(prefix_name, exe_path, name.strip())
        self.generate_launcher(prefix_name, name.strip(), icon_path)
        self.refresh_data()
        self.toast.show_message(
            f"¡'{name.strip()}' vinculado y lanzador creado con éxito!"
        )

    @Slot(str, str)
    def _on_chest_run_program(self, prefix_name: str, game_name: str) -> None:
        """Spawns asynchronous subprocess to execute the specific windows game executable."""
        game_info = self.db.get_game(game_name)
        if not game_info:
            return

        env, runner_path = self.get_wine_env(
            prefix_name,
            game_info.get("recipe_id", "default_gaming"),
            game_info.get("runner"),
        )

        exe_for_arch = Path(game_info.get("exe", "")) if game_info else None
        wine_cmd = self._get_wine_cmd(runner_path, exe_for_arch)

        # Check virtual desktop
        vd_enabled = bool(game_info.get("virtual_desktop", False))
        vd_res = game_info.get("virtual_desktop_res", "1920x1080")

        # Calculate working directory (cwd)
        exe_file = Path(game_info["exe"])
        game_dir = exe_file.parent
        relative_exe = exe_file.name

        # Subfolder root resolution (e.g. x64/Grim Dawn.exe)
        if (
            game_dir.name.lower() in ["x64", "bin64", "bin", "win64", "x86"]
            and game_dir.parent.name.lower() != "drive_c"
        ):
            game_dir = game_dir.parent
            relative_exe = f"{exe_file.parent.name}/{exe_file.name}"

        # Sandbox Isolation Logic: Apply filesystem lockdown dynamically
        sandbox_enabled = bool(game_info.get("sandbox", False))
        if sandbox_enabled:
            prefix_path = self.db.get_prefixes_dir() / prefix_name
            dosdevices_path = prefix_path / "dosdevices"
            if dosdevices_path.exists():
                z_drive = dosdevices_path / "z:"
                if z_drive.is_symlink() or z_drive.exists():
                    try:
                        z_drive.unlink()
                    except Exception:
                        pass

            # Unlink steamuser folders so they don't leak user's /home directories
            user_dir = prefix_path / "drive_c" / "users" / "steamuser"
            if user_dir.exists():
                for folder in [
                    "Desktop",
                    "Documents",
                    "Downloads",
                    "Music",
                    "Pictures",
                    "Videos",
                ]:
                    f_path = user_dir / folder
                    if f_path.is_symlink():
                        try:
                            f_path.unlink()
                            f_path.mkdir(parents=True, exist_ok=True)
                        except Exception:
                            pass

        wrappers = detect_performance_wrapper()
        if vd_enabled:
            cmd = wrappers + [
                wine_cmd,
                "explorer",
                f"/desktop=Thatch,{vd_res}",
                relative_exe,
            ]
        else:
            cmd = wrappers + [wine_cmd, relative_exe]

        log_path = self.db.get_prefixes_dir() / prefix_name / "thatch_last_run.log"
        log_file = open(log_path, "w")
        subprocess.Popen(
            cmd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setpgrp,
            cwd=str(game_dir),
        )
        self.toast.show_message(f"Iniciando {game_name}...")

        launch_mode = self.db.get_launch_mode()
        if launch_mode == "extreme":
            sys.exit(0)
        elif launch_mode == "stealth":
            self.hide()

    @Slot(str, str)
    def _on_chest_runner_changed(self, prefix_name: str, runner_name: str) -> None:
        """Saves custom overridden runner settings for prefix games and regenerates launchers."""
        games = self.db.list_games()
        updated = False
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                ginfo["runner"] = runner_name
                updated = True

                # Regenerate launcher scripts to apply the new runner executable path!
                if ginfo.get("exe") and ginfo.get("exe") != "Contenedor de Sistema":
                    icon_path = None
                    if Path(ginfo["exe"]).exists():
                        icon_path = self._extract_exe_icon(
                            prefix_name, Path(ginfo["exe"]), gname
                        )
                    self.generate_launcher(prefix_name, gname, icon_path)

        if updated:
            self.db.save()
            self._sync_recipe_change(prefix_name, "recommended_runner", runner_name)
            self.toast.show_message(
                "Configuración de runner guardada y lanzadores regenerados."
            )

    def _sync_recipe_change(
        self, prefix_name: str, key: str, value: any, subkey: str | None = None
    ) -> None:
        """Helper to dynamically synchronize Chest prefix modifications back to its recipe JSON file."""
        recipe_id = "default_gaming"
        for gname, ginfo in self.db.list_games().items():
            if ginfo.get("prefix") == prefix_name:
                recipe_id = ginfo.get("recipe_id", "default_gaming")
                break

        recipe_path = self.db.recipes_dir / f"{recipe_id}.json"
        if recipe_path.exists():
            try:
                import json

                with open(recipe_path, "r", encoding="utf-8") as f:
                    recipe_data = json.load(f)

                if subkey:
                    if key not in recipe_data or not isinstance(recipe_data[key], dict):
                        recipe_data[key] = {}
                    recipe_data[key][subkey] = value
                else:
                    recipe_data[key] = value

                with open(recipe_path, "w", encoding="utf-8") as f:
                    json.dump(recipe_data, f, indent=2, ensure_ascii=False)

                self.recipes = self.db.load_recipes()
            except Exception as e:
                print(
                    f"[Sync Error] Failed to synchronize changes to {recipe_path.name}: {e}"
                )

    def _add_verb_to_recipe(self, prefix_name: str, verb: str) -> None:
        recipe_id = "default_gaming"
        for gname, ginfo in self.db.list_games().items():
            if ginfo.get("prefix") == prefix_name:
                recipe_id = ginfo.get("recipe_id", "default_gaming")
                break

        recipe_path = self.db.recipes_dir / f"{recipe_id}.json"
        if recipe_path.exists():
            try:
                import json

                with open(recipe_path, "r", encoding="utf-8") as f:
                    recipe_data = json.load(f)

                verbs = recipe_data.get("required_verbs", [])
                if verb not in verbs:
                    verbs.append(verb)
                    recipe_data["required_verbs"] = verbs
                    with open(recipe_path, "w", encoding="utf-8") as f:
                        json.dump(recipe_data, f, indent=2, ensure_ascii=False)
                    self.recipes = self.db.load_recipes()
            except Exception as e:
                print(
                    f"[Sync Error] Failed to add verb {verb} to {recipe_path.name}: {e}"
                )

    def _remove_verb_from_recipe(self, prefix_name: str, verb: str) -> None:
        recipe_id = "default_gaming"
        for gname, ginfo in self.db.list_games().items():
            if ginfo.get("prefix") == prefix_name:
                recipe_id = ginfo.get("recipe_id", "default_gaming")
                break

        recipe_path = self.db.recipes_dir / f"{recipe_id}.json"
        if recipe_path.exists():
            try:
                import json

                with open(recipe_path, "r", encoding="utf-8") as f:
                    recipe_data = json.load(f)

                verbs = recipe_data.get("required_verbs", [])
                if verb in verbs:
                    verbs.remove(verb)
                    recipe_data["required_verbs"] = verbs
                    with open(recipe_path, "w", encoding="utf-8") as f:
                        json.dump(recipe_data, f, indent=2, ensure_ascii=False)
                    self.recipes = self.db.load_recipes()
            except Exception as e:
                print(
                    f"[Sync Error] Failed to remove verb {verb} from {recipe_path.name}: {e}"
                )

    @Slot(str, bool, bool, bool)
    def _on_chest_perf_settings_changed(
        self, prefix_name: str, esync: bool, fsync: bool, sandbox: bool
    ) -> None:
        self._sync_recipe_change(
            prefix_name, "performance_env", "1" if esync else "0", "WINEESYNC"
        )
        self._sync_recipe_change(
            prefix_name, "performance_env", "1" if fsync else "0", "WINEMFSYNC"
        )

        # Save sandbox setting to game config
        games = self.db.list_games()
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                ginfo["sandbox"] = sandbox
        self.db.save()

        # Regenerate launchers to apply the new performance env variables to the shell script!
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                if ginfo.get("exe") and "Contenedor de Sistema" not in ginfo.get("exe"):
                    icon_path = None
                    if Path(ginfo["exe"]).exists():
                        icon_path = self._extract_exe_icon(
                            prefix_name, Path(ginfo["exe"]), gname
                        )
                    self.generate_launcher(prefix_name, gname, icon_path)

        self.toast.show_message("Configuración sincronizada y lanzadores regenerados.")

    @Slot(str, bool, str)
    def _on_chest_virtual_desktop_changed(
        self, prefix_name: str, enabled: bool, resolution: str
    ) -> None:
        """Persists virtual desktop setting to all games in this prefix."""
        games = self.db.list_games()
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                ginfo["virtual_desktop"] = enabled
                ginfo["virtual_desktop_res"] = resolution

                # Regenerate launchers to apply/remove virtual desktop explorer wrap
                if ginfo.get("exe") and ginfo.get("exe") != "Contenedor de Sistema":
                    icon_path = None
                    if Path(ginfo["exe"]).exists():
                        icon_path = self._extract_exe_icon(
                            prefix_name, Path(ginfo["exe"]), gname
                        )
                    self.generate_launcher(prefix_name, gname, icon_path)

        self.db.save()
        state = f"{resolution}" if enabled else "desactivado"
        self.toast.show_message(f"Escritorio virtual {state}. Lanzadores regenerados.")

    @Slot(str, int)
    def _on_chest_dpi_scale_changed(self, prefix_name: str, dpi: int) -> None:
        """Persists DPI scale to all games in this prefix and applies it to the running WINEPREFIX."""
        games = self.db.list_games()
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                ginfo["dpi_scale"] = dpi
        self.db.save()

        # Apply DPI immediately to the WINEPREFIX registry so next launch picks it up
        associated_game = next(
            (g for g in games.values() if g.get("prefix") == prefix_name), None
        )
        recipe_id = (
            associated_game.get("recipe_id", "default_gaming")
            if associated_game
            else "default_gaming"
        )
        env, runner_path = self.get_wine_env(
            prefix_name,
            recipe_id,
            associated_game.get("runner") if associated_game else None,
        )

        wine_cmd = "wine"
        if runner_path and runner_path.exists():
            bin_dir = (
                runner_path / "files" / "bin"
                if (runner_path / "files").exists()
                else runner_path / "bin"
            )
            wine_cmd = str(bin_dir / "wine")

        try:
            import subprocess as sp

            sp.run(
                [
                    wine_cmd,
                    "reg",
                    "add",
                    r"HKCU\Control Panel\Desktop",
                    "/v",
                    "LogPixels",
                    "/t",
                    "REG_DWORD",
                    "/d",
                    str(dpi),
                    "/f",
                ],
                env=env,
                stdout=sp.DEVNULL,
                stderr=sp.DEVNULL,
                timeout=10,
            )
            label = {96: "100%", 120: "125%", 144: "150%", 192: "200%"}.get(
                dpi, f"{dpi} DPI"
            )
            self.toast.show_message(
                f"Escalado DPI aplicado al cofre: {dpi} DPI ({label})."
            )
        except Exception:
            self.toast.show_message(
                "DPI guardado — se aplicará en el próximo inicio de Wine."
            )

    @Slot(str, str)
    def _on_chest_monitor_changed(self, prefix_name: str, monitor_name: str) -> None:
        """Persists launch screen selection to all games in this prefix and regenerates launchers."""
        games = self.db.list_games()
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                ginfo["target_monitor"] = monitor_name

                # Regenerate launchers to apply primary monitor swap if needed
                if ginfo.get("exe") and ginfo.get("exe") != "Contenedor de Sistema":
                    icon_path = None
                    if Path(ginfo["exe"]).exists():
                        icon_path = self._extract_exe_icon(
                            prefix_name, Path(ginfo["exe"]), gname
                        )
                    self.generate_launcher(prefix_name, gname, icon_path)

        self.db.save()
        label = (
            "Por defecto" if monitor_name == "default" else f"Pantalla: {monitor_name}"
        )
        self.toast.show_message(
            f"Pantalla de lanzamiento guardada: {label}. Lanzadores regenerados."
        )

    @Slot(str, str)
    def _on_chest_run_installer(self, prefix_name: str, installer_path: str) -> None:
        associated_game = None
        for gname, ginfo in self.db.list_games().items():
            if ginfo.get("prefix") == prefix_name:
                associated_game = ginfo
                break
        recipe_id = (
            associated_game.get("recipe_id", "default_gaming")
            if associated_game
            else "default_gaming"
        )
        env, runner_path = self.get_wine_env(
            prefix_name,
            recipe_id,
            associated_game.get("runner") if associated_game else None,
        )

        # Detect installer architecture → auto-select wine/wine64 + WINEARCH
        installer_arch = self._get_pe_arch(installer_path)
        wine_cmd = self._get_wine_cmd(runner_path, installer_path)
        if installer_arch == "x64":
            env["WINEARCH"] = "win64"
            self.toast.show_message(
                "Instalador x64 detectado → usando wine64 con prefijo 64-bit..."
            )
        else:
            env.pop("WINEARCH", None)

        # Mount the specific directory containing the installer as virtual drive D:
        # This keeps the sandbox 100% locked (no Z: pointing to /) while giving Wine access ONLY to the installer's parent folder!
        setup_file = Path(installer_path)
        setup_dir = setup_file.parent
        d_drive = self.db.get_prefixes_dir() / prefix_name / "dosdevices" / "d:"

        if d_drive.is_symlink() or d_drive.exists():
            try:
                d_drive.unlink()
            except Exception:
                pass
        try:
            (self.db.get_prefixes_dir() / prefix_name / "dosdevices").mkdir(
                parents=True, exist_ok=True
            )
            d_drive.symlink_to(setup_dir)
        except Exception:
            pass

        vd_enabled = (
            bool(associated_game.get("virtual_desktop", False))
            if associated_game
            else False
        )
        vd_res = (
            associated_game.get("virtual_desktop_res", "1920x1080")
            if associated_game
            else "1920x1080"
        )

        args = []
        if vd_enabled:
            args = ["explorer", f"/desktop=Thatch,{vd_res}", installer_path]
        else:
            args = [installer_path]

        try:
            # Record current registry program IDs before installer runs
            self._pre_install_program_ids = {
                p["id"] for p in self.get_wine_installed_programs(prefix_name)
            }

            self.toast.show_message("Instalador iniciado en segundo plano...")

            # Spawn installer asynchronously via QProcess so we can trigger the link dialog ONLY when it exits!
            # Keeps user desktop completely clean during installation process!
            self.installer_process = QProcess()
            # Start from the full system environment (preserves WAYLAND_DISPLAY, XDG_RUNTIME_DIR,
            # DBUS_SESSION_BUS_ADDRESS, etc.) and overlay our Wine/performance env on top.
            q_env = QProcessEnvironment.systemEnvironment()
            for k, v in env.items():
                q_env.insert(k, v)
            self.installer_process.setProcessEnvironment(q_env)

            def on_installer_finished(exit_code, exit_status, p=prefix_name):
                # Clean up virtual drive D: mount
                if d_drive.is_symlink() or d_drive.exists():
                    try:
                        d_drive.unlink()
                    except Exception:
                        pass
                self._show_post_installer_dialog(p)

            self.installer_process.finished.connect(on_installer_finished)
            self.installer_process.start(wine_cmd, args)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Fallo al iniciar el instalador: {e}")

    def _show_post_installer_dialog(self, prefix_name: str) -> None:
        """Non-blocking dialog that guides user to link the game exe after installation finishes."""
        drive_c = self.db.get_prefixes_dir() / prefix_name / "drive_c"

        dialog = QDialog(self)
        dialog.setWindowTitle("Vincular juego instalado")
        dialog.setMinimumWidth(460)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        lbl_icon = QLabel("💿")
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet("font-size: 36px; margin-bottom: 4px;")
        layout.addWidget(lbl_icon)

        lbl_title = QLabel("Instalador en ejecución")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        layout.addWidget(lbl_title)

        lbl_msg = QLabel(
            "El instalador está corriendo en segundo plano.\n"
            "Cuando <b>termine la instalación</b>, haz clic en "
            "<b>Vincular Ejecutable</b> para registrar el juego en la biblioteca "
            "y crear su ícono de acceso directo."
        )
        lbl_msg.setTextFormat(Qt.RichText)
        lbl_msg.setWordWrap(True)
        lbl_msg.setAlignment(Qt.AlignCenter)
        lbl_msg.setStyleSheet("color: #a1a1aa; font-size: 13px; line-height: 1.5;")
        layout.addWidget(lbl_msg)

        btn_link = QPushButton("🔗  Vincular Ejecutable del Juego")
        btn_link.setObjectName("BlueBtn")
        btn_link.setCursor(Qt.PointingHandCursor)
        btn_link.setMinimumHeight(40)

        def do_link():
            dialog.accept()

            # 1. Let's find if there are new registry entries
            post_programs = self.get_wine_installed_programs(prefix_name)
            pre_ids = getattr(self, "_pre_install_program_ids", set())
            new_programs = [p for p in post_programs if p["id"] not in pre_ids]

            # Reset the tracked pre-install IDs
            self._pre_install_program_ids = set()

            linked_any = False
            for reg in new_programs:
                detected_exe = self.detect_game_exe(prefix_name, reg)
                if detected_exe:
                    confirm = QMessageBox.question(
                        self,
                        "Vincular Juego Detectado",
                        f"Hemos detectado un nuevo juego instalado:\n\n"
                        f"Nombre: {reg['name']}\n"
                        f"Ejecutable: {detected_exe.name}\n\n"
                        f"¿Deseas vincularlo automáticamente y crear accesos directos?",
                        QMessageBox.Yes | QMessageBox.No,
                    )
                    if confirm == QMessageBox.Yes:
                        self.db.add_game(
                            name=reg["name"],
                            exe=str(detected_exe),
                            runner=self.db.data["global_config"].get("default_runner")
                            or "Wine del Sistema (/usr/bin/wine)",
                            prefix=prefix_name,
                            recipe_id="default_gaming",
                        )
                        icon_path = self._extract_exe_icon(
                            prefix_name, detected_exe, reg["name"]
                        )
                        self.generate_launcher(prefix_name, reg["name"], icon_path)
                        linked_any = True

            if linked_any:
                self.refresh_data()
                self.toast.show_message(
                    "¡Juego detectado vinculado y lanzador creado con éxito!"
                )
                return

            # 2. Fallback to manual selection if nothing was auto-linked
            start_dir = str(drive_c) if drive_c.exists() else ""
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Seleccionar ejecutable del juego instalado",
                start_dir,
                "Executables (*.exe)",
            )
            if path:
                self._on_chest_add_program(prefix_name, exe_path_override=path)

        btn_link.clicked.connect(do_link)
        layout.addWidget(btn_link)

        btn_later = QPushButton("Cerrar — vincularé después")
        btn_later.setStyleSheet(
            "background: transparent; color: #71717a; border: none; font-size: 12px;"
        )
        btn_later.setCursor(Qt.PointingHandCursor)
        btn_later.clicked.connect(dialog.reject)
        layout.addWidget(btn_later)

        dialog.show()  # Non-blocking so the installer keeps running

    def _queue_winetricks_injections(self, prefix_name: str, verbs: list[str]) -> None:
        if not hasattr(self, "winetricks_queue"):
            self.winetricks_queue = []
            self.winetricks_queue_prefix = ""

        self.winetricks_queue.extend(verbs)
        self.winetricks_queue_prefix = prefix_name

        if not (self.process and self.process.state() == QProcess.Running):
            self._process_next_winetricks_queue()

    def _process_next_winetricks_queue(self) -> None:
        if not hasattr(self, "winetricks_queue") or not self.winetricks_queue:
            self.toast.show_message(
                "¡Inyección incremental del mapa completada con éxito!"
            )
            self.refresh_data()
            return

        next_verb = self.winetricks_queue.pop(0)
        self._on_chest_install_dependency(self.winetricks_queue_prefix, next_verb)

    @Slot(str)
    def _on_runner_downloaded(self, name: str) -> None:
        """Invoked when a wine runner is successfully downloaded asynchronously."""
        self.refresh_data()

    @Slot(str)
    def _on_toast_requested(self, message: str) -> None:
        """Triggers a floating toast overlay with the requested message."""
        self.toast.show_message(message)

    @Slot(str, str)
    def _on_chest_install_dependency(
        self, prefix_name: str, verb: str, reuse_dialog: bool = False
    ) -> None:
        """Asynchronously runs winetricks to install the dependency."""
        self.current_prefix = prefix_name
        self.current_verb = verb

        associated_game = None
        for gname, ginfo in self.db.list_games().items():
            if ginfo.get("prefix") == prefix_name:
                associated_game = ginfo
                break
        recipe_id = (
            associated_game.get("recipe_id", "default_gaming")
            if associated_game
            else "default_gaming"
        )
        env, _ = self.get_wine_env(prefix_name, recipe_id)

        if not reuse_dialog or not self.console_dialog:
            self.console_dialog = WinetricksConsoleDialog(verb, prefix_name, self)

        self.console_dialog.setWindowTitle(f"Injecting {verb} into {prefix_name}")
        self.console_dialog.console.append(
            f"\n:: [THATCH] Running winetricks for component: {verb}"
        )
        self.console_dialog.btn_close.setEnabled(False)

        # Sandbox compatibility layer: If Sandbox is enabled, temporarily restore Z: drive
        # so Winetricks has root paths access to extract/download components,
        # we will unlink it automatically as soon as it finishes!
        sandbox_enabled = (
            bool(associated_game.get("sandbox", False)) if associated_game else False
        )
        if sandbox_enabled:
            prefix_path = self.db.get_prefixes_dir() / prefix_name
            z_drive = prefix_path / "dosdevices" / "z:"
            if not z_drive.exists():
                try:
                    z_drive.symlink_to("/")
                except Exception:
                    pass

        self.process = QProcess()
        q_env = QProcessEnvironment.systemEnvironment()
        for k, v in env.items():
            q_env.insert(k, v)
        self.process.setProcessEnvironment(q_env)

        self.process.readyReadStandardOutput.connect(self._on_winetricks_stdout)
        self.process.readyReadStandardError.connect(self._on_winetricks_stderr)
        self.process.finished.connect(self._on_winetricks_finished)

        self.process.start("winetricks", ["-q", "--force", verb])
        if not self.console_dialog.isVisible():
            self.console_dialog.show()

    @Slot()
    def _on_winetricks_stdout(self) -> None:
        if self.process and self.console_dialog:
            data = (
                self.process.readAllStandardOutput()
                .data()
                .decode("utf-8", errors="ignore")
            )
            self.console_dialog.console.append(data)

    @Slot()
    def _on_winetricks_stderr(self) -> None:
        if self.process and self.console_dialog:
            data = (
                self.process.readAllStandardError()
                .data()
                .decode("utf-8", errors="ignore")
            )
            self.console_dialog.console.append(data)

    @Slot(int, QProcess.ExitStatus)
    def _on_winetricks_finished(
        self, exit_code: int, exit_status: QProcess.ExitStatus
    ) -> None:
        if self.console_dialog:
            self.console_dialog.console.append(
                f"\n:: [WINETRICKS] Process completed with code: {exit_code}"
            )

            if exit_code == 0:
                self.register_installed_verb(self.current_prefix, self.current_verb)
                self._add_verb_to_recipe(self.current_prefix, self.current_verb)
                self.refresh_data()
                self.toast.show_message(
                    f"¡Componente '{self.current_verb}' instalado con éxito!"
                )
            else:
                self.toast.show_message(
                    f"Advertencia: falló instalación de '{self.current_verb}'."
                )

        # Re-lock sandbox: If a queue finishes or is fully empty, check if prefix is sandboxed
        # and dynamically destroy the temporary 'z:' drive link!
        if not (hasattr(self, "winetricks_queue") and self.winetricks_queue):
            associated_game = None
            for gname, ginfo in self.db.list_games().items():
                if ginfo.get("prefix") == self.current_prefix:
                    associated_game = ginfo
                    break
            sandbox_enabled = (
                bool(associated_game.get("sandbox", False))
                if associated_game
                else False
            )
            if sandbox_enabled:
                prefix_path = self.db.get_prefixes_dir() / self.current_prefix
                z_drive = prefix_path / "dosdevices" / "z:"
                if z_drive.is_symlink() or z_drive.exists():
                    try:
                        z_drive.unlink()
                    except Exception:
                        pass

        if hasattr(self, "winetricks_queue") and self.winetricks_queue:
            next_verb = self.winetricks_queue.pop(0)
            self._on_chest_install_dependency(
                self.winetricks_queue_prefix, next_verb, reuse_dialog=True
            )
        else:
            if self.console_dialog:
                self.console_dialog.btn_close.setEnabled(True)
            if (
                hasattr(self, "winetricks_queue_prefix")
                and self.winetricks_queue_prefix
            ):
                self.toast.show_message(
                    "¡Inyección incremental del mapa completada con éxito!"
                )
                self.winetricks_queue_prefix = ""

    @Slot(str, str)
    def _on_chest_remove_dependency(self, prefix_name: str, verb: str) -> None:
        """Removes the verb record from winetricks.log logfile to allow reinstalls."""
        prefix_path = self.db.get_prefixes_dir() / prefix_name
        log_path = prefix_path / "winetricks.log"
        if log_path.exists():
            try:
                lines = []
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                with open(log_path, "w", encoding="utf-8") as f:
                    for line in lines:
                        if not (
                            verb in line
                            and ("w_workaround" in line or "winetricks" in line)
                        ):
                            f.write(line)

                self._remove_verb_from_recipe(prefix_name, verb)
                self.refresh_data()
                self.toast.show_message(f"Registro '{verb}' desasociado.")
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Error al remover dependencia: {e}"
                )

    # ─── CARGO STORE VIEW ACTIONS ──────────────────────────────────────────────

    @Slot(str, str, str)
    def _on_cargo_install_requested(
        self, app_name: str, recipe_id: str, target_prefix: str
    ) -> None:
        """
        Applies a Treasure Map to an existing Chest.
        Compares verbs in the recipe against winetricks.log to skip duplicates,
        then injects missing verbs sequentially.
        """
        recipe = self.recipes.get(recipe_id, {})
        required_verbs = recipe.get("required_verbs", [])

        if not required_verbs:
            self.toast.show_message(
                f"El mapa '{app_name}' no requiere dependencias de Winetricks."
            )
            return

        installed = self.get_installed_verbs(target_prefix)
        missing_verbs = [v for v in required_verbs if v not in installed]

        if not missing_verbs:
            self.toast.show_message(
                f"¡Todas las dependencias del mapa '{app_name}' ya están instaladas!"
            )
            return

        # Confirm and queue missing verbs
        confirm = QMessageBox.question(
            self,
            "Aplicar Mapa del Tesoro",
            f"El mapa '{app_name}' requiere {len(required_verbs)} dependencias.\n"
            f"Ya instaladas: {len(required_verbs) - len(missing_verbs)}\n"
            f"Faltantes por inyectar: {', '.join(missing_verbs)}\n\n"
            f"¿Deseas proceder con la inyección incremental?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            self._queue_winetricks_injections(target_prefix, missing_verbs)

    @Slot(str, str, str, str, bool)
    def _on_cargo_installation_finished(
        self,
        game_name: str,
        exe_path: str,
        prefix_name: str,
        recipe_id: str,
        auto_install: bool,
    ) -> None:
        self.generate_launcher(prefix_name, game_name)
        self.refresh_data()
        self.toast.show_message(
            f"¡Instalación de '{game_name}' completada y lanzador directo de Wine creado!"
        )

    def on_language_changed(self, index: int) -> None:
        selected_lang = self.preferences_view.combo_language.itemData(index)
        if not selected_lang:
            return
        from i18n import set_active_lang

        set_active_lang(selected_lang)
        self.retranslate()

    def retranslate(self) -> None:
        """Cascades translation updates throughout the application's visual interface."""
        self.setWindowTitle(f"🏴‍☠️ Thatch - {_('app_title')} v{__version__}")

        # Retranslate system tray menu items if tray exists
        if self.tray_icon and self.tray_icon.contextMenu():
            menu = self.tray_icon.contextMenu()
            actions = menu.actions()
            if len(actions) >= 2:
                actions[0].setText(
                    "Show Thatch" if ACTIVE_LANG == "en" else "Mostrar Thatch"
                )
                actions[1].setText("Exit" if ACTIVE_LANG == "en" else "Salir")

        # Retranslate widgets
        self.sidebar.retranslate()
        self.preferences_view.retranslate()
        self.refresh_data()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Re-adjust toast overlay position on window resize
        if hasattr(self, "toast"):
            self.toast.adjust_position()

    def closeEvent(self, event) -> None:
        if hasattr(self, "tray_icon") and self.tray_icon is not None and self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            from i18n import _

            self.tray_icon.showMessage(
                "Thatch",
                "Thatch sigue ejecutándose en segundo plano."
                if _("app_title") == "Thatch - Comandante Nativo de Wine"
                else "Thatch is still running in the background.",
                QSystemTrayIcon.Information,
                2000,
            )
        else:
            event.accept()


if __name__ == "__main__":
    from i18n import load_lang_from_db

    load_lang_from_db()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    gui = ThatchLauncher()
    gui.show()
    sys.exit(app.exec())
