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
    QProgressBar,
    QWidget,
)
from PySide6.QtCore import QTimer, QProcess, QProcessEnvironment, Qt
from views import InstallChestSelectorDialog, CreateChestWizard
from core.wine import get_wine_env, get_wine_cmd, get_pe_arch
from core.registry import get_wine_installed_programs, detect_game_exe
from core.launchers import extract_exe_icon, generate_launcher
from i18n import _


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
            lambda: prompt_installer_launch(parent_launcher, install_path, target_chest),
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


def run_native_innoextract(parent_launcher, prefix_name: str, installer_path: str) -> bool:
    """
    Natively extracts InnoSetup / FitGirl setup payloads directly on Linux using innoextract
    without invoking Wine or GUI wizards.
    """
    import subprocess
    import shutil
    from pathlib import Path

    setup_file = Path(installer_path).resolve()
    game_folder_name = setup_file.stem.replace("[FitGirl Repack]", "").strip()
    if game_folder_name.lower().startswith("setup"):
        game_folder_name = setup_file.parent.name.replace("[FitGirl Repack]", "").strip()

    prefix_path = parent_launcher.db.get_prefixes_dir() / prefix_name
    drive_c = prefix_path / "drive_c"
    target_app_dir = drive_c / "Games" / game_folder_name
    target_app_dir.mkdir(parents=True, exist_ok=True)

    parent_launcher.toast.show_message(
        _("installer_toast_innoextract_started", game_name=game_folder_name)
    )

    try:
        res = subprocess.run(
            ["innoextract", "-e", "-d", str(target_app_dir), str(setup_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if res.returncode != 0:
            print(
                f"[innoextract] Extraction failed (code {res.returncode}): "
                f"{(res.stderr or '').strip()[:500]}"
            )
            parent_launcher.toast.show_message(_("installer_toast_innoextract_failed"))
            return False

        app_subfolder = target_app_dir / "app"
        if app_subfolder.exists() and app_subfolder.is_dir():
            for item in app_subfolder.iterdir():
                dest = target_app_dir / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            try:
                shutil.rmtree(app_subfolder, ignore_errors=True)
            except Exception:
                pass

        tmp_subfolder = target_app_dir / "tmp"
        if tmp_subfolder.exists():
            try:
                shutil.rmtree(tmp_subfolder, ignore_errors=True)
            except Exception:
                pass

        parent_launcher.toast.show_message(_("installer_toast_innoextract_done"))
        show_post_installer_dialog(parent_launcher, prefix_name)
        return True
    except Exception as e:
        print(f"[innoextract] Failed to run native extraction: {e}")
        return False


def run_chest_installer(parent_launcher, prefix_name: str, installer_path: str) -> None:
    """Spawns asynchronous Wine installer process or native innoextract for the target chest."""
    setup_file = Path(installer_path).resolve()
    setup_dir = setup_file.parent

    # Detect if installer is a repack (FitGirl, Dodi, ElAmigos) with custom compressed bin payloads
    is_repack = False
    if setup_dir.exists():
        repack_files = (
            list(setup_dir.glob("fg-*.bin"))
            + list(setup_dir.glob("doi-*.bin"))
            + list(setup_dir.glob("cls-*.dll"))
            + list(setup_dir.glob("unarc.dll"))
            + list(setup_dir.glob("*.bin"))
        )
        if repack_files:
            is_repack = True

    # Bypass innoextract for FitGirl / repack installers because innoextract cannot unpack custom fg-*.bin archives
    if not is_repack and shutil.which("innoextract"):
        try:
            if run_native_innoextract(parent_launcher, prefix_name, installer_path):
                if getattr(parent_launcher, "is_installer_mode", False):
                    QApplication.quit()
                return
        except Exception as inno_err:
            print(f"[Installer] Native extraction fallback to Wine: {inno_err}")

    associated_game = None
    for gname, ginfo in parent_launcher.db.list_games().items():
        if ginfo.get("prefix") == prefix_name:
            associated_game = ginfo
            break
    sandbox_flag = bool(associated_game.get("sandbox", False)) if associated_game else False

    recipe_id = (
        associated_game.get("recipe_id", "default_gaming") if associated_game else "default_gaming"
    )
    runner_override = associated_game.get("runner") if associated_game else None
    if not runner_override or runner_override == "Wine del Sistema (/usr/bin/wine)":
        runners = parent_launcher._get_runners_list()
        for r in runners:
            if any(k in r.lower() for k in ("proton", "ge", "lutris")):
                runner_override = r
                break

    env, runner_path = get_wine_env(
        parent_launcher.db,
        parent_launcher.active_gpu,
        parent_launcher.recipes,
        prefix_name,
        recipe_id,
        runner_override,
    )

    prefix_path = parent_launcher.db.get_prefixes_dir() / prefix_name
    drive_c = prefix_path / "drive_c"
    windows_dir = drive_c / "windows"
    syswow64 = windows_dir / "syswow64"

    installer_arch = get_pe_arch(installer_path)
    wine_cmd = get_wine_cmd(parent_launcher.db, runner_path, installer_path)
    if installer_arch == "x64" or syswow64.exists():
        env["WINEARCH"] = "win64"

    # Wine preferido para repacks (solo afecta al proceso del instalador, no a
    # la selección de runner de la UI): el wine verificado tiene 32-bit nativo
    # y dispatch de syscalls estable. GE-Proton 10-34 crashea el decompresor
    # 64-bit del instalador (access violation determinística en la página de
    # dispatch -> unarc -11), así que se evita si hay alternativa.
    if is_repack:
        verified_wine = Path(
            "/usr/share/steam/compatibilitytools.d/proton-cachyos-slr/files/bin/wine"
        )
        if verified_wine.exists():
            wine_cmd = str(verified_wine)
            lib_dir = verified_wine.parent.parent / "lib"
            env["PATH"] = f"{verified_wine.parent}:{env.get('PATH', '')}"
            env["LD_LIBRARY_PATH"] = f"{lib_dir}:{env.get('LD_LIBRARY_PATH', '')}"

    # Configure all environment variables BEFORE wineboot/wineserver initialization
    # Sync backend para instaladores (receta verificada):
    # - Con WINEESYNC=0/WINEFSYNC=0 estos wines caen a ntsync, y ntsync no
    #   soporta PulseEvent -> spinlocks en los workers de descompresión
    #   (instaladores clavados en el primer archivo grande).
    # - Forzar esync resuelve el spinlock; WINENTSYNC=0 desactiva ntsync en los
    #   builds que lo soportan. WINE_DISABLE_NTSYNC/WINE_DISABLE_FAST_SYNC no
    #   tienen efecto en GE-Proton 10-34 (verificado empíricamente), por lo que
    #   no se usan.
    apply_repack_install_env(env)

    # Terminate any lingering wineserver before initializing prefix so wineserver inherits clean env
    import subprocess

    try:
        wineserver_bin = (
            Path(wine_cmd).parent / "wineserver"
            if Path(wine_cmd).parent.name in ("bin", "files")
            else "wineserver"
        )
        subprocess.run(
            [str(wineserver_bin), "-k"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    # Pre-initialize brand new Wine prefix cleanly using wineboot -u if system.reg does not exist yet
    system_reg = prefix_path / "system.reg"
    if not system_reg.exists():
        try:
            parent_launcher.toast.show_message(_("installer_toast_prefix_init"))
        except Exception:
            pass
        wineboot_bin = (
            Path(wine_cmd).parent / "wineboot"
            if Path(wine_cmd).parent.name in ("bin", "files")
            else "wineboot"
        )
        try:
            init_env = dict(env)
            init_env.pop("WINEDLLOVERRIDES", None)
            wineboot_bin = Path(wine_cmd).parent / "wineboot"
            if wineboot_bin.exists():
                wineboot_cmd = [str(wineboot_bin), "-u"]
            else:
                # Los runners tipo Proton no traen binario wineboot propio
                wineboot_cmd = [wine_cmd, "wineboot", "-u"]
            subprocess.run(
                wineboot_cmd,
                env=init_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
            )
        except Exception as boot_err:
            print(f"[Installer] Prefix wineboot initialization warning: {boot_err}")

    # Ensure Windows 10 mode in user.reg (prevent legacy winxp/win7 fallback locks)
    user_reg = prefix_path / "user.reg"
    if user_reg.exists():
        try:
            reg_txt = user_reg.read_text(encoding="utf-8", errors="ignore")
            reg_txt = reg_txt.replace('"Version"="winxp"', '"Version"="win10"').replace(
                '"Version"="win7"', '"Version"="win10"'
            )
            user_reg.write_text(reg_txt, encoding="utf-8")
        except Exception:
            pass

    # Ensure writeable drive_c directories (Games, Temp, AppData, system32, syswow64) exist in prefix
    (drive_c / "Games").mkdir(parents=True, exist_ok=True)
    (drive_c / "windows" / "temp").mkdir(parents=True, exist_ok=True)
    (drive_c / "users" / "steamuser" / "Temp").mkdir(parents=True, exist_ok=True)
    (drive_c / "users" / "steamuser" / "AppData" / "Local" / "Temp").mkdir(
        parents=True, exist_ok=True
    )

    setup_file = Path(installer_path).resolve()
    setup_dir = setup_file.parent

    # Pre-create specific game folder for CLS.ini ldmfTempPath={app} swap file creation
    game_folder_name = setup_file.stem.replace("[FitGirl Repack]", "").strip()
    if game_folder_name.lower().startswith("setup"):
        game_folder_name = setup_dir.name.replace("[FitGirl Repack]", "").strip()

    target_app_dir = drive_c / "Games" / game_folder_name
    target_app_dir.mkdir(parents=True, exist_ok=True)

    system32 = drive_c / "windows" / "system32"
    system32.mkdir(parents=True, exist_ok=True)
    syswow64.mkdir(parents=True, exist_ok=True)

    # Auto-inject installer helper DLLs using proper architecture separation (32-bit to syswow64, 64-bit to system32)
    if setup_dir.exists():
        for dll_file in setup_dir.rglob("*.dll"):
            try:
                arch = get_pe_arch(dll_file)
                if arch == "x64":
                    shutil.copy2(dll_file, system32 / dll_file.name)
                else:
                    if syswow64.exists():
                        shutil.copy2(dll_file, syswow64 / dll_file.name)
                    else:
                        shutil.copy2(dll_file, system32 / dll_file.name)
            except Exception:
                pass

    dosdevices_dir = prefix_path / "dosdevices"
    dosdevices_dir.mkdir(parents=True, exist_ok=True)
    z_drive = dosdevices_dir / "z:"
    if not z_drive.exists() and not z_drive.is_symlink():
        try:
            z_drive.symlink_to("/")
        except Exception:
            pass

    # Map D: drive symlink to installer directory to eliminate DOS wildcard bracket parsing issues ([FitGirl Repack])
    d_drive = dosdevices_dir / "d:"
    if d_drive.is_symlink() or d_drive.exists():
        try:
            d_drive.unlink()
        except Exception:
            pass
    try:
        d_drive.symlink_to(setup_dir)
    except Exception:
        pass

    setup_target = str(setup_file)

    vd_enabled = bool(associated_game.get("virtual_desktop", False) if associated_game else False)
    vd_res = associated_game.get("virtual_desktop_res", "800x600") if associated_game else "800x600"

    if vd_enabled:
        setup_win_target = f"D:\\{setup_file.name}"
        args = [
            "explorer",
            f"/desktop=Thatch,{vd_res}",
            setup_win_target,
        ]
    else:
        args = [
            setup_target,
        ]

    # Dynamically resolve all temp directories under drive_c/users and drive_c/windows/temp
    temp_dirs = [str(setup_dir)]
    if prefix_path.exists():
        users_dir = prefix_path / "drive_c" / "users"
        if users_dir.exists():
            for t_dir in users_dir.rglob("Temp"):
                if t_dir.is_dir():
                    temp_dirs.append(str(t_dir))
    win_temp = prefix_path / "drive_c" / "windows" / "temp"
    if win_temp.exists():
        temp_dirs.append(str(win_temp))

    path_prefix = ":".join(temp_dirs)
    env["PATH"] = f"{path_prefix}:{env.get('PATH', '')}"

    # Enable native unarc.dll and ISDone.dll overrides so InnoSetup decompression procedures load without 'Could not call proc' error
    dll_overrides = "unarc=n,b;isdone=n,b;mscoree=d;mshtml=d;atl100=n,b"
    if "WINEDLLOVERRIDES" in env and env["WINEDLLOVERRIDES"]:
        env["WINEDLLOVERRIDES"] = f"{env['WINEDLLOVERRIDES']};{dll_overrides}"
    else:
        env["WINEDLLOVERRIDES"] = dll_overrides

    try:
        parent_launcher._pre_install_program_ids = {
            p["id"]
            for p in get_wine_installed_programs(parent_launcher.db.get_prefixes_dir(), prefix_name)
        }

        parent_launcher.toast.show_message(_("installer_toast_started"))

        parent_launcher.installer_process = QProcess()
        parent_launcher.installer_process.setWorkingDirectory(str(setup_dir))

        q_env = QProcessEnvironment.systemEnvironment()
        for k, v in env.items():
            q_env.insert(k, v)
        parent_launcher.installer_process.setProcessEnvironment(q_env)

        # Boost CPU/IO priority and maintain missing aliases dynamically every 3 seconds while installer runs
        parent_launcher._boost_timer = QTimer()
        parent_launcher._boost_timer.setInterval(3000)
        parent_launcher._boost_timer.timeout.connect(
            lambda: _boost_process_priority(
                parent_launcher.installer_process.processId(), pref_path
            )
        )
        parent_launcher._boost_timer.start()

        def on_installer_finished(exit_code, exit_status, p=prefix_name):
            if hasattr(parent_launcher, "_boost_timer") and parent_launcher._boost_timer:
                try:
                    parent_launcher._boost_timer.stop()
                except Exception:
                    pass
            if d_drive.is_symlink() or d_drive.exists():
                try:
                    d_drive.unlink()
                except Exception:
                    pass
            if sandbox_flag:
                from core.sandbox import enforce_sandbox

                enforce_sandbox(parent_launcher.db.get_prefixes_dir() / p)

        # Terminate any lingering wineserver process from previous runner versions to prevent version mismatch crashes
        import subprocess

        try:
            wineserver_bin = (
                Path(wine_cmd).parent / "wineserver"
                if Path(wine_cmd).parent.name in ("bin", "files")
                else "wineserver"
            )
            subprocess.run(
                [str(wineserver_bin), "-k"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

        log_file_path = str(parent_launcher.db.user_data_dir / "installer_last_run.log")
        parent_launcher.installer_process.setStandardOutputFile(log_file_path)
        parent_launcher.installer_process.setStandardErrorFile(log_file_path)

        parent_launcher.installer_process.finished.connect(on_installer_finished)
        parent_launcher.installer_process.start(wine_cmd, args)

        # Show live progress monitor dialog immediately so user sees real-time extracted MBs & progress
        show_post_installer_dialog(parent_launcher, prefix_name)

        # Boost CPU and Disk I/O priority and fix missing decompressor aliases
        pref_path = parent_launcher.db.get_prefixes_dir() / prefix_name
        QTimer.singleShot(
            1000,
            lambda: _boost_process_priority(
                parent_launcher.installer_process.processId(), pref_path
            ),
        )
        QTimer.singleShot(
            3000,
            lambda: _boost_process_priority(
                parent_launcher.installer_process.processId(), pref_path
            ),
        )
    except Exception as e:
        parent_widget = parent_launcher if isinstance(parent_launcher, QWidget) else None
        QMessageBox.critical(
            parent_widget, _("installer_error_title"), _("installer_error_start_msg", error=e)
        )


def apply_repack_install_env(env: dict[str, str]) -> dict[str, str]:
    """Applies the verified repack-installer environment tuning in place.

    Empirically verified against GE-Proton / proton-cachyos runners; the
    comments inside document which failure mode each variable fixes.
    """
    env["NO_AT_BRIDGE"] = "1"
    env["XLIB_SKIP_ARGB_VISUALS"] = "1"

    # Sync backend para instaladores (receta verificada):
    # - Con WINEESYNC=0/WINEFSYNC=0 estos wines caen a ntsync, y ntsync no
    #   soporta PulseEvent -> spinlocks en los workers de descompresión
    #   (instaladores clavados en el primer archivo grande).
    # - Forzar esync resuelve el spinlock; WINENTSYNC=0 desactiva ntsync en los
    #   builds que lo soportan. WINE_DISABLE_NTSYNC/WINE_DISABLE_FAST_SYNC no
    #   tienen efecto en GE-Proton 10-34 (verificado empíricamente), por lo que
    #   no se usan.
    env["WINEESYNC"] = "1"
    env["WINEFSYNC"] = "0"
    env["WINENTSYNC"] = "0"

    # Suppress cmd.exe move/copy overwrite confirmation prompts (prevent FitGirl batch script hangs)
    env["COPYCMD"] = "/Y"
    env["DIRCMD"] = "/O:N"

    # Limit xtool, srep, and lolz decompressor thread contention on Linux anonymous pipes (prevent pipe deadlocks)
    env["XTOOL_THREADS"] = "4"
    env["SREP_THREADS"] = "4"
    env["LOLZ_THREADS"] = "4"
    env["MAX_THREADS"] = "4"

    # Enable Large Address Aware (LAA=1) to allow 32-bit processes up to 4GB virtual address space
    # Repack decompressors (unarc.dll / cls-lolz.exe) require >2GB RAM buffers during extraction
    env["PROTON_FORCE_LARGE_ADDRESS_AWARE"] = "1"
    env["WINE_LARGE_ADDRESS_AWARE"] = "1"

    # Enable native unarc.dll and ISDone.dll overrides so InnoSetup decompression procedures load without 'Could not call proc' error
    dll_overrides = "unarc=n,b;isdone=n,b;mscoree=d;mshtml=d;atl100=n,b"
    if "WINEDLLOVERRIDES" in env and env["WINEDLLOVERRIDES"]:
        env["WINEDLLOVERRIDES"] = f"{env['WINEDLLOVERRIDES']};{dll_overrides}"
    else:
        env["WINEDLLOVERRIDES"] = dll_overrides

    return env


def _boost_process_priority(pid: int, prefix_dir: Path | None = None) -> None:
    """Elevates CPU priority (renice -10) and Disk I/O priority (ionice RealTime) for installer processes and provides missing aliases."""
    import subprocess

    if prefix_dir and prefix_dir.exists():
        temp_base = prefix_dir / "drive_c" / "users"
        if temp_base.exists():
            for tmp_folder in temp_base.rglob("is-*.tmp"):
                if tmp_folder.is_dir():
                    # Prefer 64-bit decompressors (x64) on 64-bit Wine to prevent 32-bit virtual memory address space exhaustion (unarc.dll error -12)
                    alias_groups = [
                        ("cls-magic2l_x64.exe", ["cls-magic2_x64.exe", "cls-magic2.exe"]),
                        ("cls-lolz_x64.exe", ["cls-lolzx_x64.exe", "cls-lolz.exe"]),
                        ("cls-srep_x64.exe", ["cls-srep.exe"]),
                        ("cls-lollypop_x64.exe", ["cls-lollypop.exe"]),
                        ("cls-magic2_x86.exe", ["cls-magic2.exe"]),
                        ("cls-lolz_x86.exe", ["cls-lolz.exe"]),
                        ("cls-srep_x86.exe", ["cls-srep.exe"]),
                        ("cls-lollypop_x86.exe", ["cls-lollypop.exe"]),
                    ]
                    for source_file, targets in alias_groups:
                        src = tmp_folder / source_file
                        if src.exists():
                            for target in targets:
                                t = tmp_folder / target
                                if not t.exists():
                                    try:
                                        shutil.copy2(src, t)
                                    except Exception:
                                        pass

    target_pids = set()
    if pid > 0:
        target_pids.add(str(pid))
        # Find descendant PIDs (installer decompressor children live one or two
        # levels below the setup process). Scanning the whole process table for
        # 'setup' would renice unrelated user processes.
        try:
            out = subprocess.check_output(
                ["pgrep", "-P", str(pid)], stderr=subprocess.DEVNULL
            ).decode()
            children = [p.strip() for p in out.split() if p.strip()]
            target_pids.update(children)
            for child in children:
                try:
                    grandchildren = subprocess.check_output(
                        ["pgrep", "-P", child], stderr=subprocess.DEVNULL
                    ).decode()
                    target_pids.update(p.strip() for p in grandchildren.split() if p.strip())
                except Exception:
                    pass
        except Exception:
            pass

    for p in target_pids:
        try:
            subprocess.run(
                ["renice", "-n", "-10", "-p", p],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["ionice", "-c", "1", "-n", "0", "-p", p],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def show_post_installer_dialog(parent_launcher, prefix_name: str) -> None:
    """Non-blocking dialog that guides user to link the game exe after installation finishes."""
    drive_c = parent_launcher.db.get_prefixes_dir() / prefix_name / "drive_c"

    dialog = QDialog(parent_launcher)
    dialog.setWindowTitle(_("installer_link_dialog_title"))
    dialog.setMinimumWidth(460)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(24, 24, 24, 20)
    layout.setSpacing(14)

    lbl_icon = QLabel("💿")
    lbl_icon.setAlignment(Qt.AlignCenter)
    lbl_icon.setStyleSheet("font-size: 36px; margin-bottom: 4px;")
    layout.addWidget(lbl_icon)

    lbl_title = QLabel(_("installer_lbl_running"))
    lbl_title.setAlignment(Qt.AlignCenter)
    lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
    layout.addWidget(lbl_title)

    lbl_msg = QLabel(_("installer_lbl_running_msg"))
    lbl_msg.setTextFormat(Qt.RichText)
    lbl_msg.setWordWrap(True)
    lbl_msg.setAlignment(Qt.AlignCenter)
    lbl_msg.setStyleSheet("color: #a1a1aa; font-size: 13px; line-height: 1.5;")
    layout.addWidget(lbl_msg)

    progress_bar = QProgressBar()
    progress_bar.setRange(0, 0)
    progress_bar.setStyleSheet("""
        QProgressBar {
            background-color: #1e1e2e;
            border: 1px solid #313244;
            border-radius: 6px;
            height: 14px;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #89b4fa;
            border-radius: 5px;
        }
    """)
    layout.addWidget(progress_bar)

    games_dir = drive_c / "Games"
    timer = QTimer(dialog)
    timer.setInterval(1500)

    def update_status():
        import subprocess

        is_running = False
        if hasattr(parent_launcher, "installer_process") and parent_launcher.installer_process:
            if parent_launcher.installer_process.state() == QProcess.Running:
                is_running = True

        if not is_running:
            try:
                out = subprocess.check_output(
                    ["pgrep", "-i", "-f", "setup"], stderr=subprocess.DEVNULL
                ).decode()
                if out.strip():
                    is_running = True
            except Exception:
                pass

        total_bytes = 0
        if games_dir.exists():
            for p in games_dir.rglob("*"):
                if p.is_file() and not p.is_symlink():
                    try:
                        total_bytes += p.stat().st_size
                    except Exception:
                        pass

        total_mb = total_bytes / (1024 * 1024)
        if is_running:
            lbl_title.setText(_("installer_status_progress"))
            lbl_msg.setText(_("installer_status_extracting_msg", total_mb=f"{total_mb:.1f}"))
        else:
            timer.stop()
            progress_bar.setRange(0, 100)
            progress_bar.setValue(100)
            progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #1e1e2e;
                    border: 1px solid #313244;
                    border-radius: 6px;
                    height: 14px;
                }
                QProgressBar::chunk {
                    background-color: #a6e3a1;
                    border-radius: 5px;
                }
            """)
            lbl_icon.setText("🎉")
            lbl_title.setText(_("installer_status_done_title"))
            lbl_msg.setText(_("installer_status_done_msg", total_mb=f"{total_mb:.1f}"))

    timer.timeout.connect(update_status)
    timer.start()
    update_status()

    btn_link = QPushButton(_("installer_btn_link"))
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
                    _("installer_detected_title"),
                    _(
                        "installer_detected_msg",
                        name=reg["name"],
                        exe=detected_exe.name,
                    ),
                    QMessageBox.Yes | QMessageBox.No,
                )
                if confirm == QMessageBox.Yes:
                    parent_launcher.db.add_game(
                        name=reg["name"],
                        exe=str(detected_exe),
                        runner=parent_launcher.db.data["global_config"].get("default_runner")
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
            parent_launcher.toast.show_message(_("installer_toast_auto_linked"))
            return

        start_dir = str(drive_c) if drive_c.exists() else ""
        path, _filter = QFileDialog.getOpenFileName(
            parent_launcher,
            _("installer_select_exe_title"),
            start_dir,
            "Executables (*.exe)",
        )
        if path:
            parent_launcher._on_chest_add_program(prefix_name, exe_path_override=path)

    btn_link.clicked.connect(do_link)
    layout.addWidget(btn_link)

    btn_later = QPushButton(_("installer_btn_later"))
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
