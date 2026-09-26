import re
import shlex
import shutil
import subprocess
from pathlib import Path
from database import ThatchDB
from hardware import detect_performance_wrapper
from core.wine import get_wine_env, get_wine_cmd
from core.sandbox import detect_prefix_user, enforce_sandbox


def clean_game_name(game_name: str) -> str:
    """Sanitizes a game name for use in file names, .desktop ids and shell contexts.

    Whitelist approach: only word characters and dashes survive, so registry
    DisplayNames containing quotes, $, ;, backticks or newlines can neither
    break nor weaponize the generated .sh launchers and .desktop files.
    Unicode letters are preserved to stay compatible with previously generated
    launcher file names for non-ASCII game titles.
    """
    cleaned = re.sub(r"[^\w-]+", "_", str(game_name).lower()).strip("_")
    return cleaned or "game"


def get_desktop_paths() -> list[Path]:
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


def refresh_desktop_database() -> None:
    """Notifies Linux desktop environment to refresh application panel menus."""
    apps_dir = Path.home() / ".local" / "share" / "applications"
    if apps_dir.exists():
        try:
            apps_dir.touch()
        except Exception:
            pass
    if shutil.which("update-desktop-database"):
        try:
            subprocess.run(
                ["update-desktop-database", str(apps_dir)],
                capture_output=True,
                timeout=3,
            )
        except Exception:
            pass


def extract_exe_icon(prefix_name: str, exe_path: Path, game_name: str) -> Path | None:
    """
    Tries to extract the icon from a Windows .exe using icoextract or wrestool (icoutils).
    Saves the PNG to ~/.local/share/icons/thatch/<prefix>/<clean_name>.png.
    Returns the Path if successful, else None.
    """
    clean_name = clean_game_name(game_name)
    icons_dir = Path.home() / ".local" / "share" / "icons" / "thatch" / prefix_name
    icons_dir.mkdir(parents=True, exist_ok=True)
    out_png = icons_dir / f"{clean_name}.png"

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


def generate_launcher(
    db: ThatchDB,
    active_gpu: str,
    recipes: dict,
    prefix_name: str,
    game_name: str,
    icon_path: Path | None = None,
) -> None:
    """Generates static independent launcher script (.sh) and desk shortcut (.desktop) for the game."""
    game_info = db.get_game(game_name)
    if not game_info:
        return

    prefix_path = db.get_prefixes_dir() / prefix_name
    launchers_dir = prefix_path / "launchers"
    launchers_dir.mkdir(parents=True, exist_ok=True)

    clean_name = clean_game_name(game_name)
    sh_path = launchers_dir / f"{clean_name}.sh"

    env, runner_path = get_wine_env(
        db,
        active_gpu,
        recipes,
        prefix_name,
        game_info.get("recipe_id", "default_gaming"),
        game_info.get("runner"),
    )

    exe_for_arch = Path(game_info.get("exe", "")) if game_info else None
    wine_cmd = get_wine_cmd(db, runner_path, exe_for_arch)
    target_monitor = game_info.get("target_monitor", "default")

    try:
        with open(sh_path, "w", encoding="utf-8") as f:
            f.write("#!/bin/bash\n")
            safe_comment = " ".join(str(game_name).split())
            f.write(f"# Lanzador directo de {safe_comment} generado por Thatch\n\n")

            if target_monitor != "default":
                f.write('OLD_PRIMARY=$(xrandr --query | grep " primary" | cut -d" " -f1)\n')
                f.write(f"TARGET_MONITOR={shlex.quote(str(target_monitor))}\n")
                f.write(
                    'if [ -n "$TARGET_MONITOR" ] && [ "$TARGET_MONITOR" != "$OLD_PRIMARY" ]; then\n'
                )
                f.write('    xrandr --output "$TARGET_MONITOR" --primary\n')
                f.write('    trap "xrandr --output $OLD_PRIMARY --primary" EXIT INT TERM\n')
                f.write("fi\n\n")

            clean_sys_path = "/usr/local/bin:/usr/bin:/bin"
            runner_bin = ""

            if runner_path and runner_path.exists():
                bin_dir = (
                    runner_path / "files" / "bin"
                    if (runner_path / "files").exists()
                    else runner_path / "bin"
                )
                runner_bin = f"{bin_dir}:"

            f.write(f"export WINEPREFIX={shlex.quote(str(env['WINEPREFIX']))}\n")
            f.write(f"export PATH={shlex.quote(runner_bin + clean_sys_path)}\n")

            if "LD_LIBRARY_PATH" in env:
                f.write(f"export LD_LIBRARY_PATH={shlex.quote(env['LD_LIBRARY_PATH'])}\n")
            f.write(f"export WINETRICKS_CACHE={shlex.quote(str(env['WINETRICKS_CACHE']))}\n")

            recipe = recipes.get(game_info.get("recipe_id", "default_gaming"), {})
            perf_env = recipe.get("performance_env", {})
            for k, v in perf_env.items():
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(k)):
                    print(f"[Launcher Error] Skipping unsafe env key from recipe: {k!r}")
                    continue
                f.write(f"export {k}={shlex.quote(str(v))}\n")

            sandbox_enabled = bool(game_info.get("sandbox", False))
            if sandbox_enabled:
                # Lock immediately at generation time (not only at launch) and
                # emit the self-healing runtime block with the REAL prefix user.
                enforce_sandbox(prefix_path)
                win_user = detect_prefix_user(prefix_path).replace('"', "").replace("\\", "")
                f.write("\n# Zeus Sandbox Isolation: Restrict disk and user folders access\n")
                f.write('if [ -d "$WINEPREFIX/dosdevices" ]; then\n')
                f.write('    rm -f "$WINEPREFIX/dosdevices/z:"\n')
                f.write(f'    user_dir="$WINEPREFIX/drive_c/users/{win_user}"\n')
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

            exe_file = Path(game_info["exe"])
            game_dir = exe_file.parent
            relative_exe = exe_file.name

            if (
                game_dir.name.lower() in ["x64", "bin64", "bin", "win64", "x86"]
                and game_dir.parent.name.lower() != "drive_c"
            ):
                game_dir = game_dir.parent
                relative_exe = f"{exe_file.parent.name}/{exe_file.name}"

            f.write(
                f"\n# Entrar al directorio de trabajo del juego\n"
                f"cd {shlex.quote(str(game_dir))}\n\n"
            )

            wrappers = detect_performance_wrapper()
            wrapper_str = "".join(shlex.quote(w) + " " for w in wrappers)

            vd_enabled = bool(game_info.get("virtual_desktop", False))
            vd_res = game_info.get("virtual_desktop_res", "1920x1080")
            if vd_enabled:
                f.write(
                    f"{wrapper_str}{shlex.quote(str(wine_cmd))} explorer "
                    f"/desktop=Thatch,{shlex.quote(str(vd_res))} "
                    f'{shlex.quote(relative_exe)} "$@"\n'
                )
            else:
                f.write(
                    f'{wrapper_str}{shlex.quote(str(wine_cmd))} {shlex.quote(relative_exe)} "$@"\n'
                )

        sh_path.chmod(0o755)

        icon_str = str(icon_path) if (icon_path and icon_path.exists()) else "wine"

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

        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        desktop_path = desktop_dir / f"thatch-{prefix_name}-{clean_name}.desktop"

        with open(desktop_path, "w", encoding="utf-8") as f:
            f.write(desktop_content)

        for desk_p in get_desktop_paths():
            target_desk_shortcut = desk_p / f"thatch-{prefix_name}-{clean_name}.desktop"
            try:
                with open(target_desk_shortcut, "w", encoding="utf-8") as f:
                    f.write(desktop_content)
                target_desk_shortcut.chmod(0o755)
            except Exception as desk_err:
                print(f"[Desktop Shortcut Error] Failed to write to {desk_p.name}: {desk_err}")

        refresh_desktop_database()

    except Exception as e:
        print(f"[Launcher Error] Failed to generate launchers: {e}")


def remove_launcher(db: ThatchDB, prefix_name: str, game_name: str) -> None:
    """Removes the launcher script (.sh) and desk shortcut (.desktop) cleanly from the system."""
    clean_name = clean_game_name(game_name)

    desktop_dir = Path.home() / ".local" / "share" / "applications"
    if desktop_dir.exists():
        target_pattern = f"thatch-{prefix_name}-{clean_name}*.desktop"
        for dt_file in desktop_dir.glob(target_pattern):
            try:
                dt_file.unlink()
            except Exception as e:
                print(f"[Launcher Cleanup] Failed to remove desktop file {dt_file.name}: {e}")

    for desk_p in get_desktop_paths():
        target_pattern = f"thatch-{prefix_name}-{clean_name}*.desktop"
        for dt_file in desk_p.glob(target_pattern):
            try:
                dt_file.unlink()
            except Exception as e:
                print(
                    f"[Launcher Cleanup] Failed to remove Desktop shortcut {dt_file.name} from {desk_p.name}: {e}"
                )

    prefix_path = db.get_prefixes_dir() / prefix_name
    sh_path = prefix_path / "launchers" / f"{clean_name}.sh"
    if sh_path.exists():
        try:
            sh_path.unlink()
        except Exception as e:
            print(f"[Launcher Cleanup] Failed to remove sh launcher: {e}")

    refresh_desktop_database()


def cleanup_orphaned_launchers(db: ThatchDB) -> int:
    """Scans ~/.local/share/applications/ for thatch-*.desktop shortcuts whose target games/prefixes no longer exist."""
    apps_dir = Path.home() / ".local" / "share" / "applications"
    if not apps_dir.exists():
        return 0

    existing_games = db.list_games()
    valid_desktop_files = set()
    for gname, ginfo in existing_games.items():
        pname = ginfo.get("prefix", "")
        cname = clean_game_name(gname)
        valid_desktop_files.add(f"thatch-{pname}-{cname}.desktop")

    removed_count = 0
    for dt_file in apps_dir.glob("thatch-*.desktop"):
        if dt_file.name not in valid_desktop_files:
            try:
                dt_file.unlink()
                removed_count += 1
            except Exception as e:
                print(f"[Orphan Cleanup] Failed to remove {dt_file.name}: {e}")

    for desk_p in get_desktop_paths():
        for dt_file in desk_p.glob("thatch-*.desktop"):
            if dt_file.name not in valid_desktop_files:
                try:
                    dt_file.unlink()
                    removed_count += 1
                except Exception as e:
                    print(f"[Orphan Cleanup] Failed to remove desktop shortcut {dt_file.name}: {e}")

    if removed_count > 0:
        refresh_desktop_database()

    return removed_count
