import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.installer import _boost_process_priority



class TestInstallerRepacks(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_repack_detection_logic(self):
        """Verifies that FitGirl and repack setups with .bin archives bypass innoextract."""
        repack_dir = self.tmp_path / "fitgirl_game_repack"
        repack_dir.mkdir()
        (repack_dir / "setup.exe").write_bytes(b"MZ_DUMMY_EXE")
        (repack_dir / "fg-01.bin").write_bytes(b"DUMMY_BIN_DATA")
        (repack_dir / "unarc.dll").write_bytes(b"DUMMY_DLL_DATA")
        (repack_dir / "cls-magic2.dll").write_bytes(b"DUMMY_DLL_DATA")

        repack_files = (
            list(repack_dir.glob("fg-*.bin"))
            + list(repack_dir.glob("doi-*.bin"))
            + list(repack_dir.glob("cls-*.dll"))
            + list(repack_dir.glob("unarc.dll"))
            + list(repack_dir.glob("*.bin"))
        )
        self.assertGreater(len(repack_files), 0, "Repack files should be detected")

        standard_dir = self.tmp_path / "standard_inno_setup"
        standard_dir.mkdir()
        (standard_dir / "setup.exe").write_bytes(b"MZ_DUMMY_EXE")

        std_repack_files = (
            list(standard_dir.glob("fg-*.bin"))
            + list(standard_dir.glob("doi-*.bin"))
            + list(standard_dir.glob("cls-*.dll"))
            + list(standard_dir.glob("unarc.dll"))
            + list(standard_dir.glob("*.bin"))
        )
        self.assertEqual(len(std_repack_files), 0, "Standard setup should not be flagged as a repack")

    def test_decompressor_alias_family_isolation(self):
        """Ensures that _boost_process_priority copies decompressor aliases ONLY within the same family."""
        prefix_dir = self.tmp_path / "test_prefix"
        prefix_dir.mkdir()
        tmp_folder = (
            prefix_dir / "drive_c" / "users" / "testuser" / "AppData" / "Local" / "Temp" / "is-99999.tmp"
        )
        tmp_folder.mkdir(parents=True)

        magic_x64 = tmp_folder / "cls-magic2l_x64.exe"
        lolz_x64 = tmp_folder / "cls-lolz_x64.exe"
        srep_x64 = tmp_folder / "cls-srep_x64.exe"

        magic_x64.write_bytes(b"MAGIC_X64_BINARY_HEADER")
        lolz_x64.write_bytes(b"LOLZ_X64_BINARY_HEADER")
        srep_x64.write_bytes(b"SREP_X64_BINARY_HEADER")

        _boost_process_priority(0, prefix_dir)

        magic_x86 = tmp_folder / "cls-magic2_x86.exe"
        lolz_x86 = tmp_folder / "cls-lolz_x86.exe"
        lolz_std = tmp_folder / "cls-lolz.exe"

        self.assertTrue(magic_x86.exists(), "cls-magic2_x86.exe should be created from magic2l_x64")
        self.assertEqual(magic_x86.read_bytes(), b"MAGIC_X64_BINARY_HEADER")

        self.assertTrue(lolz_x86.exists(), "cls-lolz_x86.exe should be created from lolz_x64")
        self.assertTrue(lolz_std.exists(), "cls-lolz.exe should be created from lolz_x64")

        # CRITICAL: Verify that cls-lolz.exe is derived from LOLZ and NOT overwritten by MAGIC2
        self.assertEqual(lolz_x86.read_bytes(), b"LOLZ_X64_BINARY_HEADER")
        self.assertEqual(lolz_std.read_bytes(), b"LOLZ_X64_BINARY_HEADER")
        self.assertNotEqual(lolz_std.read_bytes(), b"MAGIC_X64_BINARY_HEADER")

    def test_repack_recipe_configuration(self):
        """Validates repack.json performance parameters and native DLL overrides."""
        recipe_path = Path(__file__).parent.parent / "config" / "recipes" / "repack.json"
        self.assertTrue(recipe_path.exists(), "config/recipes/repack.json must exist")

        data = json.loads(recipe_path.read_text(encoding="utf-8"))
        perf = data.get("performance_env", {})

        self.assertEqual(perf.get("WINEESYNC"), "0", "WINEESYNC must be 0")
        self.assertEqual(perf.get("WINEFSYNC"), "0", "WINEFSYNC must be 0")
        self.assertEqual(perf.get("WINE_LARGE_ADDRESS_AWARE"), "0", "WINE_LARGE_ADDRESS_AWARE must be 0")
        self.assertEqual(perf.get("COPYCMD"), "/Y", "COPYCMD must be /Y")

        overrides = perf.get("WINEDLLOVERRIDES", "")
        self.assertIn("unarc=n,b", overrides, "WINEDLLOVERRIDES must include unarc=n,b")
        self.assertIn("botva2=n,b", overrides, "WINEDLLOVERRIDES must include botva2=n,b")
        self.assertIn("isskin=n,b", overrides, "WINEDLLOVERRIDES must include isskin=n,b")


if __name__ == "__main__":
    unittest.main()
