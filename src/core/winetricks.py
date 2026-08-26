import threading
import shutil
import subprocess
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QWidget,
)
from i18n import ACTIVE_LANG


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


def scan_winetricks_catalog_bg(
    db,
    on_ready_signal,
    on_failed_signal,
    on_error_signal,
    silent: bool = True,
) -> None:
    """Launches a background daemon thread to scan the full winetricks catalog and persist it in SQLite."""

    def bg_loader():
        if not shutil.which("winetricks"):
            if not silent:
                on_error_signal.emit(
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
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
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

                    display_name = verb.replace("_", " ").replace("=", ": ").title()
                    full_catalog.append(
                        {
                            "verb": verb,
                            "name": display_name,
                            "desc": wt_desc if wt_desc else display_name,
                            "type": cat_name,
                        }
                    )
            except Exception as e:
                print(f"[WinetricksCatalog BG] Failed to load {cat_name}: {e}")

        if full_catalog:
            try:
                db.save_winetricks_catalog(full_catalog)
                print(
                    f"[WinetricksCatalog BG] Successfully cached {len(full_catalog)} verbs to SQLite."
                )
                if not silent:
                    on_ready_signal.emit(len(full_catalog))
            except Exception as e:
                print(f"[WinetricksCatalog BG] Failed to cache catalog to SQLite: {e}")
        else:
            if not silent:
                on_failed_signal.emit()

    threading.Thread(target=bg_loader, daemon=True).start()
