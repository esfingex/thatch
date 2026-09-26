import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestAppSmoke(unittest.TestCase):
    """Headless instantiation of the full ThatchLauncher UI.

    Regression net for the controller refactor and the i18n migration: the
    whole view stack must build offscreen against a temporary HOME.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.fake_home = Path(self.tmp_dir.name) / "home"
        self.fake_home.mkdir(parents=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_launcher_builds_headless(self):
        from PySide6.QtWidgets import QApplication

        with patch("pathlib.Path.home", return_value=self.fake_home):
            import main as app_main

            _app = QApplication.instance() or QApplication([])
            gui = app_main.ThatchLauncher()
            self.assertGreater(gui.view_stack.count(), 0, "view stack must contain views")
            self.assertIsNotNone(gui.db)
            self.assertIsNotNone(gui.recipes)
            gui.close()

    def test_retranslate_ui_runs(self):
        from PySide6.QtWidgets import QApplication

        with patch("pathlib.Path.home", return_value=self.fake_home):
            import main as app_main
            from i18n import set_active_lang

            _app = QApplication.instance() or QApplication([])
            gui = app_main.ThatchLauncher()
            set_active_lang("en")
            gui.retranslate_ui()
            set_active_lang("es")
            gui.retranslate_ui()
            self.assertIn("Thatch", gui.windowTitle())
            gui.close()


if __name__ == "__main__":
    unittest.main()
