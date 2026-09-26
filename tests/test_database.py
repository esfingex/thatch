import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from database import ThatchDB  # noqa: E402


class TestDbRobustness(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.fake_home = self.tmp_path / "home"
        self.fake_home.mkdir()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _make_db(self) -> ThatchDB:
        with patch("pathlib.Path.home", return_value=self.fake_home):
            return ThatchDB(db_path=self.tmp_path / "thatch_db.sqlite")

    def test_prefix_migration_collision_is_preserved_not_destroyed(self):
        """Regression: a name collision used to rmtree the legacy prefix data."""
        legacy = self.fake_home / ".local" / "share" / "thatch" / "prefixes" / "colision"
        legacy.mkdir(parents=True)
        (legacy / "precious_save.txt").write_text("do not delete")

        existing = self.fake_home / "thatch" / "prefixes" / "colision"
        existing.mkdir(parents=True)
        (existing / "newer_data.txt").write_text("keep me")

        self._make_db()

        # The pre-existing prefix must survive untouched...
        self.assertTrue((existing / "newer_data.txt").exists())
        # ...and the legacy data must be preserved under a conflict name.
        conflicts = list(
            (self.fake_home / "thatch" / "prefixes").glob("colision_migrated_conflict*")
        )
        self.assertEqual(len(conflicts), 1, "legacy prefix must be moved, not deleted")
        self.assertTrue((conflicts[0] / "precious_save.txt").exists())

    def test_context_manager_commits_and_closes(self):
        db = self._make_db()
        prefixes_dir = db.get_prefixes_dir()
        game_dir = prefixes_dir / "chest1"
        game_dir.mkdir(parents=True, exist_ok=True)
        exe = game_dir / "game.exe"
        exe.write_bytes(b"MZ")

        db.add_game("Test Game", str(exe), "runner", "chest1")
        # Re-open from scratch: data must be committed and readable.
        db2 = self._make_db()
        self.assertIsNotNone(db2.get_game("Test Game"))

        db2.remove_game("Test Game")
        self.assertIsNone(self._make_db().get_game("Test Game"))

    def test_wal_mode_is_active(self):
        db = self._make_db()
        import sqlite3

        conn = sqlite3.connect(db.sqlite_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        self.assertEqual(mode.lower(), "wal")


if __name__ == "__main__":
    unittest.main()
