import sys
import tempfile
import unittest
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.sandbox import detect_prefix_user, enforce_sandbox, is_sandboxed  # noqa: E402


def _make_prefix(tmp: Path, win_user: str = "steamuser") -> Path:
    prefix = tmp / "prefixes" / "chest1"
    dosdevices = prefix / "dosdevices"
    dosdevices.mkdir(parents=True)
    user_dir = prefix / "drive_c" / "users" / win_user
    user_dir.mkdir(parents=True)
    return prefix


class TestSandbox(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.host_folder = self.tmp_path / "real_home" / "Documents"
        self.host_folder.mkdir(parents=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_enforce_removes_z_drive_and_user_links(self):
        prefix = _make_prefix(self.tmp_path)
        z_drive = prefix / "dosdevices" / "z:"
        z_drive.symlink_to("/")
        desktop_link = prefix / "drive_c" / "users" / "steamuser" / "Desktop"
        desktop_link.symlink_to(self.host_folder)

        removed = enforce_sandbox(prefix)

        self.assertGreaterEqual(removed, 2)
        self.assertFalse(z_drive.is_symlink(), "z: drive must be removed")
        self.assertFalse(desktop_link.is_symlink(), "host link must be removed")
        self.assertTrue(desktop_link.is_dir(), "clean local Desktop must be recreated")
        self.assertTrue(self.host_folder.exists(), "host target must never be touched")

    def test_enforce_is_idempotent(self):
        prefix = _make_prefix(self.tmp_path)
        (prefix / "dosdevices" / "z:").symlink_to("/")
        first = enforce_sandbox(prefix)
        second = enforce_sandbox(prefix)
        self.assertEqual(second, 0, "second pass must be a no-op")
        self.assertGreaterEqual(first, 1)

    def test_enforce_never_deletes_real_directories(self):
        prefix = _make_prefix(self.tmp_path)
        z_dir = prefix / "dosdevices" / "z:"
        z_dir.mkdir()  # real dir, NOT a symlink to /
        keeper = z_dir / "keep_me.txt"
        keeper.write_text("precious")

        enforce_sandbox(prefix)

        self.assertTrue(z_dir.is_dir(), "real z: dir must not be deleted")
        self.assertTrue(keeper.exists())

    def test_detect_prefix_user_finds_real_user(self):
        prefix = _make_prefix(self.tmp_path, win_user="gamer42")
        (prefix / "drive_c" / "users" / "Public").mkdir()
        self.assertEqual(detect_prefix_user(prefix), "gamer42")

    def test_sandbox_applies_to_non_steamuser_prefix(self):
        """Regression: sandbox was hardcoded to 'steamuser' and silently no-op'd otherwise."""
        prefix = _make_prefix(self.tmp_path, win_user="gamer42")
        docs_link = prefix / "drive_c" / "users" / "gamer42" / "Documents"
        docs_link.symlink_to(self.host_folder)
        (prefix / "dosdevices" / "z:").symlink_to("/")

        enforce_sandbox(prefix)

        self.assertFalse(docs_link.is_symlink())
        self.assertTrue((prefix / "drive_c" / "users" / "gamer42" / "Documents").is_dir())
        self.assertTrue(is_sandboxed(prefix))

    def test_is_sandboxed_reflects_open_links(self):
        prefix = _make_prefix(self.tmp_path)
        (prefix / "dosdevices" / "z:").symlink_to("/")
        self.assertFalse(is_sandboxed(prefix))
        enforce_sandbox(prefix)
        self.assertTrue(is_sandboxed(prefix))


if __name__ == "__main__":
    unittest.main()
