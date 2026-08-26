import sys
import shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QApplication,
)
from PySide6.QtCore import QTimer, QProcess, QProcessEnvironment, Qt
from views import InstallChestSelectorDialog, CreateChestWizard
from core.wine import get_wine_env, get_wine_cmd, get_pe_arch
from core.registry import get_wine_installed_programs, detect_game_exe
from core.launchers import extract_exe_icon, generate_launcher


def handle_cli_args(parent_launcher) -> None:
    """Parses command-line arguments (--install / --chest / file path) on application launch."""
    args = sys.argv[1:]
    if not args:
        return

    install_path: str | None = None
    target_chest: str | None = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--install" and i + 1 < len(args):
            install_path = args[i + 1]
            i += 2
        elif arg == "--chest" and i + 1 < len(args):
            target_chest = args[i + 1]
            i += 2
        else:
            p = Path(arg)
            if p.exists() and p.suffix.lower() in (
                ".exe",
                ".msi",
                ".bat",
                ".cmd",
            ):
                install_path = str(p)
            i += 1

    if install_path and Path(install_path).exists():
        parent_launcher.is_installer_mode = True
        QTimer.singleShot(
            200,
            lambda: prompt_installer_launch(
                parent_launcher, install_path, target_chest
            ),
        )


def prompt_installer_launch(
    parent_launcher, installer_path: str, target_chest: str | None = None
) -> None:
    """Prompts chest selection dialog for the given installer, or directly runs it if target_chest is set."""
    chests = parent_launcher.db.list_existing_prefixes()

    if target_chest and target_chest in chests:
        run_chest_installer(parent_launcher, target_chest, installer_path)
        return

    dialog = InstallChestSelectorDialog(installer_path, chests, parent=None)
    if dialog.exec() == QDialog.Accepted:
        if dialog.selected_chest:
            run_chest_installer(parent_launcher, dialog.selected_chest, installer_path)
        elif dialog.request_create_new:
            wizard = CreateChestWizard(
                parent_launcher.recipes,
                parent_launcher._get_runners_list(),
                parent=None,
            )
            wizard.created.connect(parent_launcher._on_chest_wizard_finish)
            if wizard.exec() == QDialog.Accepted:
                name = wizard.txt_chest_name.text().strip().replace(" ", "_").lower()
                parent_launcher.refresh_data()
                run_chest_installer(parent_launcher, name, installer_path)
            else:
                if getattr(parent_launcher, "is_installer_mode", False):
                    QApplication.quit()
    else:
        if getattr(parent_launcher, "is_installer_mode", False):
            QApplication.quit()


def run_chest_installer(parent_launcher, prefix_name: str, installer_path: str) -> None:
    """Spawns asynchronous Wine installer process for the target chest."""
    associated_game = None
    for gname, ginfo in parent_launcher.db.list_games().items():
        if ginfo.get("prefix") == prefix_name:
            associated_game = ginfo
            break

    recipe_id = (
        associated_game.get("recipe_id", "default_gaming")
        if associated_game
        else "default_gaming"
    )
    env, runner_path = get_wine_env(
        parent_launcher.db,
        parent_launcher.active_gpu,
        parent_launcher.recipes,
        prefix_name,
        recipe_id,
        associated_game.get("runner") if associated_game else None,
    )

    prefix_path = parent_launcher.db.get_prefixes_dir() / prefix_name
    drive_c = prefix_path / "drive_c"
    windows_dir = drive_c / "windows"
    syswow64 = windows_dir / "syswow64"

    installer_arch = get_pe_arch(installer_path)
    wine_cmd = get_wine_cmd(parent_launcher.db, runner_path, installer_path)
    if installer_arch == "x64" or syswow64.exists():
        env["WINEARCH"] = "win64"

    # Ensure writeable drive_c directories (Games, Temp, AppData, system32, syswow64) exist in prefix
    (drive_c / "Games").mkdir(parents=True, exist_ok=True)
    (drive_c / "windows" / "temp").mkdir(parents=True, exist_ok=True)
    (drive_c / "users" / "steamuser" / "Temp").mkdir(parents=True, exist_ok=True)
    (drive_c / "users" / "steamuser" / "AppData" / "Local" / "Temp").mkdir(
        parents=True, exist_ok=True
    )

    system32 = drive_c / "windows" / "system32"
    system32.mkdir(parents=True, exist_ok=True)
    syswow64.mkdir(parents=True, exist_ok=True)

    setup_file = Path(installer_path).resolve()
    setup_dir = setup_file.parent

    # Auto-inject installer helper DLLs (unarc, isdone, cls-*, atl*) directly into system32 / syswow64
    if setup_dir.exists():
        for dll_file in setup_dir.rglob("*.dll"):
            try:
                shutil.copy2(dll_file, system32 / dll_file.name)
                if syswow64.exists():
                    shutil.copy2(dll_file, syswow64 / dll_file.name)
                if windows_dir.exists():
                    shutil.copy2(dll_file, windows_dir / dll_file.name)
            except Exception:
                pass

    env["TEMP"] = "C:\\windows\\temp"
    env["TMP"] = "C:\\windows\\temp"

    dosdevices_dir = prefix_path / "dosdevices"
    dosdevices_dir.mkdir(parents=True, exist_ok=True)
    z_drive = dosdevices_dir / "z:"
    if not z_drive.exists() and not z_drive.is_symlink():
        try:
            z_drive.symlink_to("/")
        except Exception:
            pass

    # Ensure no D: symlink is present so installer defaults target destination to C:\Games\
    d_drive = dosdevices_dir / "d:"
    if d_drive.is_symlink() or d_drive.exists():
        try:
            d_drive.unlink()
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
        args = [
            "explorer",
            f"/desktop=Thatch,{vd_res}",
            str(setup_file),
            "/DIR=C:\\Games",
        ]
    else:
        args = [str(setup_file), "/DIR=C:\\Games"]

    # Force disable Esync and Fsync during setup execution to prevent cls-lolz thread deadlocks
    env["WINEESYNC"] = "0"
    env["WINEFSYNC"] = "0"
    env["WINEMFSYNC"] = "0"

    # Set LAA=0 for installer process to prevent 32-bit pointer overflow (>2GB) in unarc.dll / cls-lolz.dll
    env["PROTON_FORCE_LARGE_ADDRESS_AWARE"] = "0"
    env["WINE_LARGE_ADDRESS_AWARE"] = "0"
    env["PATH"] = f"{str(setup_dir)}:{env.get('PATH', '')}"

    dll_overrides = "mscoree=d;mshtml=d;atl100=n,b;unarc=n,b;isdone=n,b"
    if "WINEDLLOVERRIDES" in env and env["WINEDLLOVERRIDES"]:
        env["WINEDLLOVERRIDES"] = f"{env['WINEDLLOVERRIDES']};{dll_overrides}"
    else:
        env["WINEDLLOVERRIDES"] = dll_overrides

    try:
        parent_launcher._pre_install_program_ids = {
            p["id"]
            for p in get_wine_installed_programs(
                parent_launcher.db.get_prefixes_dir(), prefix_name
            )
        }

        parent_launcher.toast.show_message("Instalador iniciado en segundo plano...")

        parent_launcher.installer_process = QProcess()
        parent_launcher.installer_process.setWorkingDirectory(str(setup_dir))

        q_env = QProcessEnvironment.systemEnvironment()
        for k, v in env.items():
            q_env.insert(k, v)
        parent_launcher.installer_process.setProcessEnvironment(q_env)

        def on_installer_finished(exit_code, exit_status, p=prefix_name):
            if d_drive.is_symlink() or d_drive.exists():
                try:
                    d_drive.unlink()
                except Exception:
                    pass
            show_post_installer_dialog(parent_launcher, p)

        parent_launcher.installer_process.finished.connect(on_installer_finished)
        parent_launcher.installer_process.start(wine_cmd, args)
    except Exception as e:
        QMessageBox.critical(
            parent_launcher, "Error", f"Fallo al iniciar el instalador: {e}"
        )


def show_post_installer_dialog(parent_launcher, prefix_name: str) -> None:
    """Non-blocking dialog that guides user to link the game exe after installation finishes."""
    drive_c = parent_launcher.db.get_prefixes_dir() / prefix_name / "drive_c"

    dialog = QDialog(parent_launcher)
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

        post_programs = get_wine_installed_programs(
            parent_launcher.db.get_prefixes_dir(), prefix_name
        )
        pre_ids = getattr(parent_launcher, "_pre_install_program_ids", set())
        new_programs = [p for p in post_programs if p["id"] not in pre_ids]

        parent_launcher._pre_install_program_ids = set()

        linked_any = False
        for reg in new_programs:
            detected_exe = detect_game_exe(parent_launcher.db, prefix_name, reg)
            if detected_exe:
                confirm = QMessageBox.question(
                    parent_launcher,
                    "Vincular Juego Detectado",
                    f"Hemos detectado un nuevo juego instalado:\n\n"
                    f"Nombre: {reg['name']}\n"
                    f"Ejecutable: {detected_exe.name}\n\n"
                    f"¿Deseas vincularlo automáticamente y crear accesos directos?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if confirm == QMessageBox.Yes:
                    parent_launcher.db.add_game(
                        name=reg["name"],
                        exe=str(detected_exe),
                        runner=parent_launcher.db.data["global_config"].get(
                            "default_runner"
                        )
                        or "Wine del Sistema (/usr/bin/wine)",
                        prefix=prefix_name,
                        recipe_id="default_gaming",
                    )
                    icon_path = extract_exe_icon(prefix_name, detected_exe, reg["name"])
                    generate_launcher(
                        parent_launcher.db,
                        parent_launcher.active_gpu,
                        parent_launcher.recipes,
                        prefix_name,
                        reg["name"],
                        icon_path,
                    )
                    linked_any = True

        if linked_any:
            parent_launcher.refresh_data()
            parent_launcher.toast.show_message(
                "¡Juego detectado vinculado y lanzador creado con éxito!"
            )
            return

        start_dir = str(drive_c) if drive_c.exists() else ""
        path, _ = QFileDialog.getOpenFileName(
            parent_launcher,
            "Seleccionar ejecutable del juego instalado",
            start_dir,
            "Executables (*.exe)",
        )
        if path:
            parent_launcher._on_chest_add_program(prefix_name, exe_path_override=path)

    btn_link.clicked.connect(do_link)
    layout.addWidget(btn_link)

    btn_later = QPushButton("Cerrar — vincularé después")
    btn_later.setStyleSheet(
        "background: transparent; color: #71717a; border: none; font-size: 12px;"
    )
    btn_later.setCursor(Qt.PointingHandCursor)
    btn_later.clicked.connect(dialog.reject)
    layout.addWidget(btn_later)

    def _on_dialog_finished():
        if getattr(parent_launcher, "is_installer_mode", False):
            QApplication.quit()

    dialog.finished.connect(_on_dialog_finished)
    dialog.show()
