import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.launchers import clean_game_name, generate_launcher  # noqa: E402


class StubDB:
    """Minimal ThatchDB stand-in so generate_launcher can run without Qt or a real DB."""

    def __init__(self, prefixes_dir: Path):
        self._prefixes_dir = prefixes_dir
        self.data = {"global_config": {"default_runner": ""}}

    def get_game(self, name):
        return {
            "name": name,
            "exe": str(self._prefixes_dir / "testprefix" / "drive_c" / "Games" / name / "game.exe"),
            "prefix": "testprefix",
            "runner": "",
            "recipe_id": "default_gaming",
        }

    def get_prefixes_dir(self):
        return self._prefixes_dir

    def get_runners_dir(self):
        return self._prefixes_dir.parent / "runners"

    def get_winetricks_cache_dir(self):
        return self._prefixes_dir.parent / "cache"


def _make_game_tree(prefixes_dir: Path, game_dir_name: str) -> None:
    """Creates drive_c/Games/<game_dir_name>/game.exe so hostile paths are exercised."""
    game_dir = prefixes_dir / "testprefix" / "drive_c" / "Games" / game_dir_name
    game_dir.mkdir(parents=True, exist_ok=True)
    (game_dir / "game.exe").write_bytes(b"MZ_DUMMY_EXE")


class TestLauncherInjection(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.marker = self.tmp_path / "pwn_marker"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_clean_game_name_is_shell_safe(self):
        hostile = 'Evil"; rm -rf ~ #$(touch x)`abc`\nnewline'
        cleaned = clean_game_name(hostile)
        for forbidden in ('"', "'", ";", "$", "`", "\n", " ", "/"):
            self.assertNotIn(forbidden, cleaned)

    def test_hostile_paths_cannot_inject_into_launcher(self):
        """A registry/inode path with $(...) and quotes must stay inert in the .sh."""
        payload = f'Evil$(touch {self.marker})"; rm #'
        prefixes_dir = self.tmp_path / "prefixes"
        _make_game_tree(prefixes_dir, payload)

        db = StubDB(prefixes_dir)
        with patch("pathlib.Path.home", return_value=self.tmp_path / "home"):
            generate_launcher(
                db,
                active_gpu="none",
                recipes={},
                prefix_name="testprefix",
                game_name=payload,
            )

        sh_path = prefixes_dir / "testprefix" / "launchers"
        generated = list(sh_path.glob("*.sh"))
        self.assertTrue(generated, "launcher script must be generated")
        script = generated[0]

        # Static: script must remain syntactically valid despite hostile input.
        syntax = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, f"launcher must be valid bash: {syntax.stderr}")

        # Dynamic: executing every export/cd line must NOT evaluate command
        # substitution — shlex.quote keeps them inside single quotes.
        self.marker.unlink(missing_ok=True)
        exec_check = subprocess.run(
            ["bash", "-c", f"grep -E '^(export|cd) ' {script} | bash"],
            capture_output=True,
            text=True,
        )
        self.assertFalse(
            self.marker.exists(),
            f"injection executed! bash said: {exec_check.stderr}",
        )

        # The wine launch line must also be quoted, never raw-interpolated.
        content = script.read_text(encoding="utf-8")
        self.assertNotIn(f'"{payload}"', content, "values must not be double-quoted raw")

    def test_recipe_env_keys_are_validated(self):
        """Recipe env keys must match POSIX identifier rules before being exported."""
        prefixes_dir = self.tmp_path / "prefixes"
        _make_game_tree(prefixes_dir, "Innocent Game")

        db = StubDB(prefixes_dir)
        hostile_recipe = {
            "default_gaming": {
                "performance_env": {
                    "SAFE_VAR": "1",
                    'BAD"; rm #': "x",
                }
            }
        }
        with patch("pathlib.Path.home", return_value=self.tmp_path / "home"):
            generate_launcher(
                db,
                active_gpu="none",
                recipes=hostile_recipe,
                prefix_name="testprefix",
                game_name="Innocent Game",
            )

        script = (prefixes_dir / "testprefix" / "launchers").glob("*.sh").__next__()
        content = script.read_text(encoding="utf-8")
        self.assertIn("export SAFE_VAR=", content)
        self.assertNotIn("BAD", content, "unsafe env key must be skipped")


if __name__ == "__main__":
    unittest.main()
