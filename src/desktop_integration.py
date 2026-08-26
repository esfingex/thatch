import sys
import subprocess
from pathlib import Path


def update_system_context_menu(chests: list[str]) -> bool:
    """
    Registers and updates Linux system context menu integration ("Instalar con Thatch").
    - Installs ~/.local/share/applications/thatch-installer.desktop for general file managers.
    - Registers MIME association for Windows executable types (.exe, .msi, .bat).
    - Installs KDE Dolphin ServiceMenu in ~/.local/share/kio/servicemenus/ and ~/.local/share/kservices5/ServiceMenus/
      with dynamic submenus for all installed chests.
    """
    try:
        root_dir = Path(__file__).parent.parent.resolve()
        python_exe = sys.executable
        thatch_entry = root_dir / "thatch.py"
        icon_file = root_dir / "src" / "assets" / "icon.png"

        if not thatch_entry.exists():
            return False

        # 1. Main .desktop launcher for MIME application selector
        apps_dir = Path.home() / ".local" / "share" / "applications"
        apps_dir.mkdir(parents=True, exist_ok=True)

        desktop_file = apps_dir / "thatch-installer.desktop"
        icon_str = str(icon_file) if icon_file.exists() else "system-run"

        desktop_content = f"""[Desktop Entry]
Type=Application
Name=Instalar con Thatch
Comment=Instalar programas ejecutable de Windows en un cofre de Thatch
Exec="{python_exe}" "{thatch_entry}" --install %f
Icon={icon_str}
Terminal=false
Categories=Utility;Gaming;
MimeType=application/x-ms-dos-executable;application/x-msi;application/x-bat;application/x-msdownload;application/x-executable;
NoDisplay=false
"""
        with open(desktop_file, "w", encoding="utf-8") as f:
            f.write(desktop_content)

        # Register MIME defaults via xdg-mime if available
        for mime in [
            "application/x-ms-dos-executable",
            "application/x-msi",
            "application/x-msdownload",
        ]:
            try:
                subprocess.run(
                    ["xdg-mime", "default", "thatch-installer.desktop", mime],
                    capture_output=True,
                    check=False,
                )
            except Exception:
                pass

        # Update desktop database
        try:
            subprocess.run(
                ["update-desktop-database", str(apps_dir)],
                capture_output=True,
                check=False,
            )
        except Exception:
            pass

        # 2. KDE Dolphin ServiceMenu integration (supporting submenus with all chests!)
        actions_list = ["select_chest"]
        chest_actions_blocks = []

        for chest in chests:
            safe_id = "".join(c if c.isalnum() else "_" for c in chest).lower()
            action_id = f"chest_{safe_id}"
            actions_list.append(action_id)

            block = f"""[Desktop Action {action_id}]
Name=Cofre: {chest}
Icon=package-x-generic
Exec="{python_exe}" "{thatch_entry}" --install %f --chest "{chest}"
"""
            chest_actions_blocks.append(block)

        actions_str = ";".join(actions_list) + ";"
        blocks_str = "\n".join(chest_actions_blocks)

        servicemenu_content = f"""[Desktop Entry]
Type=Service
ServiceTypes=KonqPopupMenu/Plugin
MimeType=application/x-ms-dos-executable;application/x-msi;application/x-bat;application/x-msdownload;application/x-executable;
Actions={actions_str}
X-KDE-Submenu=Instalar con Thatch

[Desktop Action select_chest]
Name=Elegir cofre en Thatch...
Icon={icon_str}
Exec="{python_exe}" "{thatch_entry}" --install %f

{blocks_str}
"""

        # Write to both KDE ServiceMenu paths for compatibility
        kservice_paths = [
            Path.home() / ".local" / "share" / "kio" / "servicemenus",
            Path.home() / ".local" / "share" / "kservices5" / "ServiceMenus",
        ]

        for s_dir in kservice_paths:
            s_dir.mkdir(parents=True, exist_ok=True)
            s_file = s_dir / "thatch_installer.desktop"
            with open(s_file, "w", encoding="utf-8") as f:
                f.write(servicemenu_content)

        return True
    except Exception as e:
        print(f"[DesktopIntegration] Error updating context menu: {e}")
        return False
