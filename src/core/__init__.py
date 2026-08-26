# ruff: noqa: F401
# core/__init__.py
from .wine import (
    get_wine_env,
    get_pe_arch,
    get_wine_cmd,
    win_to_linux_path,
)
from .registry import (
    get_wine_installed_programs,
    detect_game_exe,
)
from .launchers import (
    get_desktop_paths,
    refresh_desktop_database,
    extract_exe_icon,
    generate_launcher,
    remove_launcher,
    cleanup_orphaned_launchers,
)
from .winetricks import (
    WinetricksConsoleDialog,
    scan_winetricks_catalog_bg,
)
from .installer import (
    handle_cli_args,
    prompt_installer_launch,
    run_chest_installer,
    show_post_installer_dialog,
)
