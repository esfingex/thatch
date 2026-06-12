# views/zeus_dialog.py
import shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QButtonGroup,
    QRadioButton,
    QComboBox,
    QLineEdit,
    QCheckBox,
    QTextEdit,
    QMessageBox,
    QFileDialog,
    QWidget,
)
from PySide6.QtCore import Slot, Signal, QProcess, QProcessEnvironment

from database import ThatchDB
from hardware import compile_performance_env


class ZeusInstallerDialog(QDialog):
    """
    Modular Dialog managing interactive sandbox setup selections,
    parches repack, and async installer processes with full thread-safety.
    """

    installation_succeeded = Signal(
        str, str, str, str, bool
    )  # name, exe_path, prefix_name, recipe_id, auto_install_verbs

    def __init__(
        self,
        db: ThatchDB,
        recipes: dict,
        active_gpu: str,
        prefilled_setup: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.recipes = recipes
        self.active_gpu = active_gpu
        self.process = None
        self.target_folder_name = ""
        self.recipe_id = ""
        self.is_isolated = True
        self.prefix_path = None
        self.games_dir = None
        self.before_subdirs = set()

        self.setWindowTitle("Sandbox Installer (Zeus Engine)")
        self.resize(580, 480)
        self.layout = QFormLayout(self)
        self.layout.setSpacing(12)

        # Setup.exe selector
        setup_lay = QHBoxLayout()
        self.lbl_setup = QLabel(
            prefilled_setup if prefilled_setup else "Sin seleccionar"
        )
        self.lbl_setup.setStyleSheet(
            "font-family: monospace; font-size: 11px; color: #a0a0a0;"
        )
        btn_browse = QPushButton("Examinar")
        btn_browse.setObjectName("BlueBtn")
        btn_browse.clicked.connect(self._browse_setup)
        setup_lay.addWidget(self.lbl_setup, stretch=3)
        setup_lay.addWidget(btn_browse, stretch=1)
        self.layout.addRow("Instalador (setup.exe):", setup_lay)

        # Environment Mode Selector (Radio buttons)
        self.prefix_mode_group = QButtonGroup(self)
        self.radio_new_env = QRadioButton("Crear nuevo prefijo aislado desde receta")
        self.radio_new_env.setChecked(True)
        self.radio_existing_env = QRadioButton(
            "Instalar en un prefijo compartido existente"
        )
        self.prefix_mode_group.addButton(self.radio_new_env)
        self.prefix_mode_group.addButton(self.radio_existing_env)

        mode_lay = QVBoxLayout()
        mode_lay.addWidget(self.radio_new_env)
        mode_lay.addWidget(self.radio_existing_env)
        self.layout.addRow("Destino de Instalación:", mode_lay)

        # Existing Prefix dropdown
        self.existing_prefix_combo = QComboBox()
        self.existing_prefix_combo.addItems(self.db.list_existing_prefixes())
        self.existing_prefix_combo.setEnabled(False)
        self.layout.addRow("Prefijo Compartido:", self.existing_prefix_combo)

        # Target Recipe selection
        self.recipe_combo = QComboBox()
        for rid, rdata in self.recipes.items():
            self.recipe_combo.addItem(rdata.get("display_name", rid), rid)
        self.layout.addRow("Receta de juego:", self.recipe_combo)

        # Target Final Folder Name
        self.folder_input = QLineEdit()
        self.layout.addRow("Nombre del juego (Biblioteca):", self.folder_input)

        # Toggle widgets based on selection
        self.radio_new_env.toggled.connect(self._on_mode_changed)
        self.radio_existing_env.toggled.connect(self._on_mode_changed)

        # InnoSetup Optimization Checkbox
        self.opt_repack = QCheckBox(
            "Optimizar descompresión y direccionamiento (InnoSetup/Repacks)"
        )
        self.opt_repack.setChecked(False)  # Unchecked by default!
        self.opt_repack.setStyleSheet("color: #00e5ff; font-weight: bold;")
        self.layout.addRow("Parches del sistema:", self.opt_repack)

        # Log Console
        self.console = QTextEdit()
        self.console.setObjectName("ConsoleLog")
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(120)
        self.layout.addWidget(self.console)

        # Submit Button
        self.btn_launch = QPushButton("Iniciar Instalador Zeus")
        self.btn_launch.setObjectName("OrangeBtn")
        self.btn_launch.clicked.connect(self._run_zeus_engine)
        self.layout.addRow(self.btn_launch)

    @Slot()
    def _browse_setup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Buscar setup.exe", "", "Instaladores (*setup*.exe *setup*.bin *.exe)"
        )
        if path:
            self.lbl_setup.setText(path)

    @Slot()
    def _on_mode_changed(self) -> None:
        is_new = self.radio_new_env.isChecked()
        self.existing_prefix_combo.setEnabled(not is_new)

    @Slot()
    def _run_zeus_engine(self) -> None:
        setup_path = self.lbl_setup.text()
        self.target_folder_name = self.folder_input.text().strip()

        if setup_path == "Sin seleccionar" or not self.target_folder_name:
            QMessageBox.warning(
                self,
                "Falta Información",
                "Por favor selecciona el instalador y el nombre de la carpeta destino.",
            )
            return

        self.btn_launch.setEnabled(False)
        self.console.clear()
        self.console.append(":: [ZEUS-ENGINE] Preparando entorno de instalación...")

        self.recipe_id = self.recipe_combo.currentData()
        recipe = self.recipes.get(self.recipe_id, {})
        recipe_env = recipe.get("performance_env", {})

        env = compile_performance_env(self.active_gpu, recipe_env)
        env["WINETRICKS_CACHE"] = str(self.db.get_winetricks_cache_dir())

        if self.opt_repack.isChecked():
            env["WINEDLLOVERRIDES"] = "atl100=n;unarc,isdone=n,b"
            env["PROTON_FORCE_LARGE_ADDRESS_AWARE"] = "1"
            self.console.append(
                ":: [ZEUS-ENGINE] Optimización de descompresión y direccionamiento de memoria ACTIVADA."
            )
        else:
            self.console.append(
                ":: [ZEUS-ENGINE] Optimización de descompresión DESACTIVADA (Instalación estándar)."
            )

        selected_runner = "Wine del Sistema (/usr/bin/wine)"
        if self.parent() and hasattr(self.parent(), "details_pane"):
            selected_runner = self.parent().details_pane.combo_runners.currentText()

        runners_dir = self.db.get_runners_dir()
        runner_path = runners_dir / selected_runner

        wine_cmd = "wine"
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
            wine_cmd = str(bin_dir / "wine")

        self.is_isolated = self.radio_new_env.isChecked()

        if self.is_isolated:
            self.prefix_path = self.db.get_prefixes_dir() / "temp_zeus_prefix"
            if self.prefix_path.exists():
                shutil.rmtree(self.prefix_path, ignore_errors=True)
            self.prefix_path.mkdir(parents=True, exist_ok=True)
            self.console.append(
                f":: [ZEUS-ENGINE] Modo Aislado. Usando WINEPREFIX temporal: {self.prefix_path}"
            )
        else:
            existing_prefix_name = self.existing_prefix_combo.currentText()
            self.prefix_path = self.db.get_prefixes_dir() / existing_prefix_name
            self.console.append(
                f":: [ZEUS-ENGINE] Modo Compartido. Usando WINEPREFIX existente: {self.prefix_path}"
            )

        env["WINEPREFIX"] = str(self.prefix_path)

        # Mount the specific directory containing the installer as virtual drive D:
        # This keeps the sandbox 100% locked (no Z: pointing to /) while giving Wine access ONLY to the installer's parent folder!
        setup_file = Path(setup_path)
        setup_dir = setup_file.parent
        d_drive = self.prefix_path / "dosdevices" / "d:"

        # Remove any existing d: drive symlink first to prevent conflicts
        if d_drive.is_symlink() or d_drive.exists():
            try:
                d_drive.unlink()
            except Exception:
                pass

        try:
            (self.prefix_path / "dosdevices").mkdir(parents=True, exist_ok=True)
            d_drive.symlink_to(setup_dir)
            self.console.append(
                f":: [ZEUS-ENGINE] Mapeado '{setup_dir}' como Unidad D: virtual (Aislamiento seguro)."
            )
        except Exception as e:
            self.console.append(f":: [ZEUS-ENGINE] Advertencia al mapear Unidad D: {e}")

        self.console.append(
            ":: [ZEUS-ENGINE] Lanzando instalador setup.exe en modo asíncrono..."
        )
        self.console.append(
            ":: [ZEUS-ENGINE] IMPORTANTE: Si estás en modo aislado, instala en la ruta por defecto: C:\\Games\\"
        )

        self.before_subdirs = set()
        self.games_dir = self.prefix_path / "drive_c" / "Games"
        if not self.is_isolated and self.games_dir.exists():
            self.before_subdirs = {
                d.name for d in self.games_dir.iterdir() if d.is_dir()
            }

        self.process = QProcess()
        q_env = QProcessEnvironment()
        for k, v in env.items():
            q_env.insert(k, v)
        self.process.setProcessEnvironment(q_env)

        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)

        wineserver_cmd = str(Path(wine_cmd).parent / "wineserver")
        bash_command = f'"{wine_cmd}" "{setup_path}"; "{wineserver_cmd}" -w'
        self.process.start("bash", ["-c", bash_command])

    @Slot()
    def _on_stdout(self) -> None:
        if self.process:
            data = (
                self.process.readAllStandardOutput()
                .data()
                .decode("utf-8", errors="ignore")
            )
            self.console.append(data)

    @Slot()
    def _on_stderr(self) -> None:
        if self.process:
            data = (
                self.process.readAllStandardError()
                .data()
                .decode("utf-8", errors="ignore")
            )
            self.console.append(data)

    @Slot(int, QProcess.ExitStatus)
    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self.console.append(
            f"\n:: [ZEUS-ENGINE] Instalador finalizado con código: {exit_code}"
        )
        recipe = self.recipes.get(self.recipe_id, {})

        if self.is_isolated:
            temp_games_dir = self.prefix_path / "drive_c" / "Games"
            temp_gog_dir = self.prefix_path / "drive_c" / "GOG Games"
            install_dir = None

            if temp_games_dir.exists():
                subdirs = [d for d in temp_games_dir.iterdir() if d.is_dir()]
                if subdirs:
                    install_dir = subdirs[0]

            if not install_dir and temp_gog_dir.exists():
                subdirs = [d for d in temp_gog_dir.iterdir() if d.is_dir()]
                if subdirs:
                    install_dir = subdirs[0]

            if install_dir and install_dir.exists():
                self.console.append(
                    f":: [ZEUS-ENGINE] Carpeta de juego detectada: {install_dir.name}"
                )

                final_prefix_dir = (
                    self.db.get_prefixes_dir()
                    / self.target_folder_name.replace(" ", "_").lower()
                )
                if final_prefix_dir.exists():
                    shutil.rmtree(final_prefix_dir, ignore_errors=True)

                self.console.append(
                    f":: [ZEUS-ENGINE] Migrando prefijo completo de {self.prefix_path} a: {final_prefix_dir}"
                )

                try:
                    shutil.move(str(self.prefix_path), str(final_prefix_dir))
                    self.console.append(
                        ":: [ZEUS-ENGINE] ¡Migración del prefijo completa exitosa!"
                    )

                    migrated_game_path = (
                        final_prefix_dir / "drive_c" / "Games" / install_dir.name
                    )
                    if not migrated_game_path.exists():
                        migrated_game_path = (
                            final_prefix_dir
                            / "drive_c"
                            / "GOG Games"
                            / install_dir.name
                        )

                    # Find EXE
                    game_exe = None
                    exes = list(migrated_game_path.glob("*.exe"))
                    if exes:
                        game_exe = exes[0]
                    else:
                        exes = list(migrated_game_path.glob("**/*.exe"))
                        if exes:
                            game_exe = exes[0]

                    if game_exe:
                        self.console.append(
                            f":: [ZEUS-ENGINE] Registrando juego en biblioteca: {self.target_folder_name}"
                        )
                        self.db.add_game(
                            name=self.target_folder_name,
                            exe=str(game_exe),
                            runner=self.db.get_default_runner()
                            or "Wine del Sistema (/usr/bin/wine)",
                            prefix=final_prefix_dir.name,
                            recipe_id=self.recipe_id,
                        )
                    else:
                        self.console.append(
                            ":: [ZEUS-ENGINE] AVISO: No se detectó ejecutable. Registra el .exe manualmente."
                        )

                    required_verbs = recipe.get("required_verbs", [])
                    auto_install = False
                    if required_verbs:
                        res = QMessageBox.question(
                            self,
                            "Dependencias de Receta",
                            f"El juego se ha instalado con éxito.\nLa receta '{recipe.get('display_name', self.recipe_id)}' requiere inyectar: {', '.join(required_verbs)}.\n\n¿Deseas instalar estas dependencias automáticamente ahora?",
                            QMessageBox.Yes | QMessageBox.No,
                        )
                        if res == QMessageBox.Yes:
                            auto_install = True

                    if auto_install:
                        self.installation_succeeded.emit(
                            self.target_folder_name,
                            str(game_exe or ""),
                            final_prefix_dir.name,
                            self.recipe_id,
                            True,
                        )
                    else:
                        QMessageBox.information(
                            self,
                            "Éxito",
                            f"¡Juego '{self.target_folder_name}' instalado y registrado con éxito!",
                        )
                        self.installation_succeeded.emit(
                            self.target_folder_name,
                            str(game_exe or ""),
                            final_prefix_dir.name,
                            self.recipe_id,
                            False,
                        )
                    self.accept()
                except Exception as e:
                    self.console.append(
                        f"❌ [ZEUS-ENGINE] Error durante migración: {e}"
                    )
                    QMessageBox.critical(
                        self, "Error", f"Fallo al migrar archivos: {e}"
                    )
            else:
                self.console.append(
                    "❌ [ZEUS-ENGINE] AVISO: No se detectó carpeta instalada. ¿Se canceló la instalación?"
                )
                QMessageBox.warning(
                    self,
                    "Cancelado",
                    "Instalación no completada. Prefijo temporal preservado para inspección.",
                )
        else:
            # Existing Shared Prefix flow
            self.console.append(
                ":: [ZEUS-ENGINE] Escaneando prefijo compartido para detectar nueva instalación..."
            )
            after_subdirs = set()
            if self.games_dir.exists():
                after_subdirs = {d.name for d in self.games_dir.iterdir() if d.is_dir()}

            new_subdirs = after_subdirs - self.before_subdirs
            install_dir = None
            if new_subdirs:
                install_dir = self.games_dir / list(new_subdirs)[0]
            else:
                if self.games_dir.exists():
                    subdirs = [d for d in self.games_dir.iterdir() if d.is_dir()]
                    if subdirs:
                        install_dir = subdirs[0]

            if install_dir and install_dir.exists():
                self.console.append(
                    f":: [ZEUS-ENGINE] Nueva carpeta detectada en prefijo compartido: {install_dir.name}"
                )

                game_exe = None
                exes = list(install_dir.glob("*.exe"))
                if exes:
                    game_exe = exes[0]
                else:
                    exes = list(install_dir.glob("**/*.exe"))
                    if exes:
                        game_exe = exes[0]

                if game_exe:
                    self.console.append(
                        f":: [ZEUS-ENGINE] Registrando juego '{self.target_folder_name}' en biblioteca con exe: {game_exe.name}"
                    )
                    self.db.add_game(
                        name=self.target_folder_name,
                        exe=str(game_exe),
                        runner=self.db.get_default_runner()
                        or "Wine del Sistema (/usr/bin/wine)",
                        prefix=self.prefix_path.name,
                        recipe_id=self.recipe_id,
                    )
                else:
                    self.console.append(
                        ":: [ZEUS-ENGINE] AVISO: No se detectó ejecutable. Registra el .exe manualmente."
                    )

                required_verbs = recipe.get("required_verbs", [])

                parent_launcher = self.parent()
                installed_verbs = []
                if parent_launcher and hasattr(parent_launcher, "get_installed_verbs"):
                    installed_verbs = parent_launcher.get_installed_verbs(
                        self.prefix_path.name
                    )

                missing = [v for v in required_verbs if v not in installed_verbs]
                auto_install = False
                if missing:
                    res = QMessageBox.question(
                        self,
                        "Dependencias de Receta",
                        f"El juego se ha instalado en el prefijo compartido.\nFaltan por instalar las siguientes dependencias de la receta: {', '.join(missing)}.\n\n¿Deseas instalarlas automáticamente ahora?",
                        QMessageBox.Yes | QMessageBox.No,
                    )
                    if res == QMessageBox.Yes:
                        auto_install = True

                if auto_install:
                    self.installation_succeeded.emit(
                        self.target_folder_name,
                        str(game_exe or ""),
                        self.prefix_path.name,
                        self.recipe_id,
                        True,
                    )
                else:
                    QMessageBox.information(
                        self,
                        "Éxito",
                        f"¡Juego '{self.target_folder_name}' registrado con éxito en prefijo compartido!",
                    )
                    self.installation_succeeded.emit(
                        self.target_folder_name,
                        str(game_exe or ""),
                        self.prefix_path.name,
                        self.recipe_id,
                        False,
                    )
                self.accept()
            else:
                self.console.append(
                    "❌ [ZEUS-ENGINE] AVISO: No se detectó ninguna nueva carpeta de instalación."
                )
                QMessageBox.warning(
                    self,
                    "Aviso",
                    "No se detectó una carpeta nueva en C:\\Games. Si la instalación tuvo éxito en otra ruta, añade el juego manualmente usando 'Reclutar Juego'.",
                )
                self.accept()

        # Clean up the temporary D: drive virtual mount to prevent host directory leak
        d_drive = self.prefix_path / "dosdevices" / "d:"
        if d_drive.is_symlink() or d_drive.exists():
            try:
                d_drive.unlink()
                self.console.append(
                    ":: [ZEUS-ENGINE] Unidad D: virtual desmontada y eliminada."
                )
            except Exception:
                pass

        # Re-lock sandbox: If the prefix is sandboxed, dynamically unlink 'z:' drive again!
        prefixes_to_lock = [self.prefix_path]
        if self.is_isolated:
            final_prefix_dir = (
                self.db.get_prefixes_dir()
                / self.target_folder_name.replace(" ", "_").lower()
            )
            prefixes_to_lock.append(final_prefix_dir)

        for prefix in prefixes_to_lock:
            # Check if this prefix has sandbox enabled in the database
            associated_game = None
            for gname, ginfo in self.db.list_games().items():
                if ginfo.get("prefix") == prefix.name:
                    associated_game = ginfo
                    break
            sandbox_enabled = (
                bool(associated_game.get("sandbox", False))
                if associated_game
                else False
            )

            if sandbox_enabled:
                z_drive = prefix / "dosdevices" / "z:"
                if z_drive.is_symlink() or z_drive.exists():
                    try:
                        z_drive.unlink()
                        self.console.append(
                            f":: [ZEUS-ENGINE] Sandbox re-bloqueado con éxito para: {prefix.name}"
                        )
                    except Exception:
                        pass

        self.btn_launch.setEnabled(True)
