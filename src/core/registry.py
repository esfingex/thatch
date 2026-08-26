import os
import re
from pathlib import Path
from core.wine import win_to_linux_path


def get_wine_installed_programs(prefixes_dir: Path, prefix_name: str) -> list[dict]:
    """
    Reads Wine WINEPREFIX registry files (system.reg + user.reg) line-by-line to detect
    installed programs. Optimized to prevent memory bloat and CPU spikes on large registry files.
    """
    prefix_path = prefixes_dir / prefix_name
    drive_c = prefix_path / "drive_c"
    results: list[dict] = []
    seen_ids: set[str] = set()

    def _win_to_linux(win_path: str) -> str:
        if not win_path:
            return ""
        normalized = win_path.replace("\\\\", "\\").replace("\\", "/")
        if normalized.startswith('"') and normalized.endswith('"'):
            normalized = normalized[1:-1]

        normalized = re.sub(r"^[Cc]:/", "", normalized)
        return str(drive_c / normalized)

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

                    if line_stripped.startswith("[") and line_stripped.endswith("]"):
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

                        header = line_stripped[1:-1].lower()
                        uninstall_prefix = (
                            "software\\microsoft\\windows\\currentversion\\uninstall\\"
                        )
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

                if in_uninstall and current_app.get("name"):
                    app_id = current_app["id"]
                    if app_id not in seen_ids:
                        display_name = current_app["name"]
                        if not any(p in display_name.lower() for p in skip_patterns):
                            seen_ids.add(app_id)
                            results.append(current_app)
        except Exception as e:
            print(f"Error parsing registry file {reg_file.name}: {e}")

    return results


def detect_game_exe(db, prefix_name: str, reg_entry: dict) -> Path | None:
    """
    Attempts to automatically locate the main game executable for a registry-detected program.
    """
    display_icon = reg_entry.get("display_icon_win", "")
    if display_icon:
        cleaned = re.sub(r",-?\d+$", "", display_icon.strip().strip('"'))
        if cleaned.lower().endswith(".exe"):
            exe_path = win_to_linux_path(db, prefix_name, cleaned)
            if exe_path and exe_path.exists() and exe_path.is_file():
                return exe_path

    install_location = reg_entry.get("install_location", "")
    if install_location:
        loc_path = Path(install_location)
        if loc_path.exists() and loc_path.is_dir():
            exe_files = []
            for root, dirs, files in os.walk(loc_path):
                depth = len(Path(root).relative_to(loc_path).parts)
                if depth > 3:
                    dirs.clear()
                    continue
                for f in files:
                    if f.lower().endswith(".exe"):
                        exe_files.append(Path(root) / f)

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
                game_name = reg_entry.get("name", "").lower()
                for p in filtered_exes:
                    if p.stem.lower() in game_name or game_name in p.stem.lower():
                        return p
                try:
                    filtered_exes.sort(key=lambda x: x.stat().st_size, reverse=True)
                    return filtered_exes[0]
                except Exception:
                    pass

    return None
