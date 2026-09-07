from pathlib import Path
from database import ThatchDB
from hardware import compile_performance_env

# Directorios estándar donde viven los compatibility tools de Steam
# (motores instalados vía pacman, como proton-cachyos-slr, o por Steam).
SYSTEM_RUNNER_DIRS = [
    Path("/usr/share/steam/compatibilitytools.d"),
    Path.home() / ".steam" / "steam" / "compatibilitytools.d",
    Path.home() / ".local" / "share" / "Steam" / "compatibilitytools.d",
]


def discover_system_runners() -> list[tuple[str, Path]]:
    """Devuelve (nombre, carpeta) de los motores wine instalados a nivel de sistema."""
    found: list[tuple[str, Path]] = []
    for base in SYSTEM_RUNNER_DIRS:
        if not base.is_dir():
            continue
        for d in base.iterdir():
            if d.is_dir() and (d / "files" / "bin" / "wine").exists():
                found.append((d.name, d))
    return found


def resolve_runner_path(runners_dir: Path, runner_name: str) -> Path | None:
    """Resuelve la carpeta de un runner: primero en runners_dir, luego en los
    motores de sistema (compat tools de Steam). Los symlinks rotos en
    runners_dir caen automáticamente a la fuente de sistema."""
    local = runners_dir / runner_name
    if local.exists():
        return local
    for sys_dir in SYSTEM_RUNNER_DIRS:
        candidate = sys_dir / runner_name
        if candidate.exists():
            return candidate
    return None


def get_pe_arch(exe_path: str | Path) -> str:
    """
    Reads the PE header of an executable to determine its architecture.
    Returns 'x64' for AMD64/ARM64 binaries, 'x86' for 32-bit.
    """
    try:
        with open(exe_path, "rb") as f:
            f.seek(0x3C)
            pe_offset = int.from_bytes(f.read(4), "little")
            f.seek(pe_offset + 4)  # Skip "PE\0\0" signature
            machine = int.from_bytes(f.read(2), "little")
            if machine in (0x8664, 0xAA64):
                return "x64"
    except Exception:
        pass
    return "x86"


def get_wine_cmd(
    db: ThatchDB, runner_path: Path | None, exe_path: str | Path | None = None
) -> str:
    """
    Returns the correct wine or wine64 binary for the runner.
    Auto-detects PE32+ (x64) executables and upgrades to wine64 automatically.
    """
    if runner_path and runner_path.exists():
        bin_dir = (
            runner_path / "files" / "bin"
            if (runner_path / "files").exists()
            else runner_path / "bin"
        )
    else:
        bin_dir = None

    is_x64 = get_pe_arch(exe_path) == "x64" if exe_path else False
    wine_bin = "wine64" if is_x64 else "wine"

    if bin_dir:
        candidate = bin_dir / wine_bin
        if candidate.exists():
            return str(candidate)
        fallback = bin_dir / ("wine" if is_x64 else "wine64")
        if fallback.exists():
            return str(fallback)
        return str(bin_dir / "wine")

    # System wine fallback: prefer absolute path to bypass wrappers
    for candidate in ["/usr/bin/wine64", "/usr/bin/wine"]:
        if is_x64 and candidate == "/usr/bin/wine64" and Path(candidate).exists():
            return candidate
        if candidate == "/usr/bin/wine" and Path(candidate).exists():
            return candidate

    return wine_bin


def get_wine_env(
    db: ThatchDB,
    active_gpu: str,
    recipes: dict,
    prefix_name: str,
    recipe_id: str,
    runner_override: str | None = None,
) -> tuple[dict[str, str], Path | None]:
    """
    Compiles full execution environment variables (WINEPREFIX, LD_LIBRARY_PATH, PATH, WINEDLLPATH)
    for a specific chest and runner.
    """
    recipe = recipes.get(recipe_id, {})
    recipe_env = recipe.get("performance_env", {})

    env = compile_performance_env(active_gpu, recipe_env)
    env["WINEPREFIX"] = str(db.get_prefixes_dir() / prefix_name)
    env["WINETRICKS_CACHE"] = str(db.get_winetricks_cache_dir())
    env["WINETRICKS_DOWNLOADER"] = "curl"

    selected_runner = (
        runner_override
        if runner_override
        else (
            db.data["global_config"].get("default_runner", "")
            or "Wine del Sistema (/usr/bin/wine)"
        )
    )
    runners_dir = db.get_runners_dir()
    runner_path = resolve_runner_path(runners_dir, selected_runner)

    if runner_path:
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

        dllpaths = []
        for path in [
            lib_dir / "vkd3d",
            lib64_dir / "vkd3d",
            lib_dir / "wine",
            lib64_dir / "wine",
        ]:
            if path.exists():
                dllpaths.append(str(path))
        if dllpaths:
            if "WINEDLLPATH" in env:
                dllpaths.append(env["WINEDLLPATH"])
            env["WINEDLLPATH"] = ":".join(dllpaths)

        return env, runner_path

    return env, None


def win_to_linux_path(db: ThatchDB, prefix_name: str, win_path: str) -> Path | None:
    """Converts a Windows C:\\ path to the Linux equivalent inside drive_c."""
    if not win_path:
        return None
    import re

    win_path = re.sub(r",-?\d+$", "", win_path.strip().strip('"'))
    normalized = win_path.replace("\\\\", "\\").replace("\\", "/")
    normalized = re.sub(r"^[Cc]:/", "", normalized)

    prefix_path = db.get_prefixes_dir() / prefix_name
    drive_c = prefix_path / "drive_c"
    return drive_c / normalized
