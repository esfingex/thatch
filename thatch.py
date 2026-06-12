# ruff: noqa: E402
#!/usr/bin/env python3
import sys
import signal
from pathlib import Path

# Add src/ folder to Python module search paths
src_dir = Path(__file__).parent.resolve() / "src"
sys.path.insert(0, str(src_dir))

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from src.main import ThatchLauncher
from src.style import apply_theme

if __name__ == "__main__":
    # Allow Ctrl+C to interrupt the Qt event loop
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    icon_path = src_dir / "assets" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    apply_theme(app)
    gui = ThatchLauncher()
    gui.show()
    sys.exit(app.exec())
