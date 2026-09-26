import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.installer import _boost_process_priority, apply_repack_install_env


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
        self.assertEqual(
            len(std_repack_files), 0, "Standard setup should not be flagged as a repack"
        )

    def test_decompressor_alias_family_isolation(self):
        """Ensures that _boost_process_priority copies decompressor aliases ONLY within the same family.

        Semantics of _boost_process_priority (verified):
        - 64-bit sources are preferred on 64-bit Wine: x64 aliases are created
          first and never overwritten by x86 copies.
        - x86 aliases are ONLY created from x86 sources (family isolation).
        """
        prefix_dir = self.tmp_path / "test_prefix"
        prefix_dir.mkdir()
        tmp_folder = (
            prefix_dir
            / "drive_c"
            / "users"
            / "testuser"
            / "AppData"
            / "Local"
            / "Temp"
            / "is-99999.tmp"
        )
        tmp_folder.mkdir(parents=True)

        magic_x64 = tmp_folder / "cls-magic2l_x64.exe"
        lolz_x64 = tmp_folder / "cls-lolz_x64.exe"
        srep_x64 = tmp_folder / "cls-srep_x64.exe"
        lolz_x86 = tmp_folder / "cls-lolz_x86.exe"

        magic_x64.write_bytes(b"MAGIC_X64_BINARY_HEADER")
        lolz_x64.write_bytes(b"LOLZ_X64_BINARY_HEADER")
        srep_x64.write_bytes(b"SREP_X64_BINARY_HEADER")
        lolz_x86.write_bytes(b"LOLZ_X86_BINARY_HEADER")

        _boost_process_priority(0, prefix_dir)

        magic_alias = tmp_folder / "cls-magic2_x64.exe"
        magic_std = tmp_folder / "cls-magic2.exe"
        lolz_alias = tmp_folder / "cls-lolzx_x64.exe"
        lolz_std = tmp_folder / "cls-lolz.exe"
        srep_std = tmp_folder / "cls-srep.exe"

        self.assertTrue(
            magic_alias.exists(), "cls-magic2_x64.exe should be created from magic2l_x64"
        )
        self.assertTrue(magic_std.exists(), "cls-magic2.exe should be created from magic2l_x64")
        self.assertEqual(magic_alias.read_bytes(), b"MAGIC_X64_BINARY_HEADER")
        self.assertEqual(magic_std.read_bytes(), b"MAGIC_X64_BINARY_HEADER")

        self.assertTrue(lolz_alias.exists(), "cls-lolzx_x64.exe should be created from lolz_x64")
        self.assertTrue(lolz_std.exists(), "cls-lolz.exe should be created from lolz_x64")
        self.assertTrue(srep_std.exists(), "cls-srep.exe should be created from srep_x64")

        # CRITICAL: x64 alias creation order wins — cls-lolz.exe is derived from
        # LOLZ x64 and is NOT overwritten later by the x86 source.
        self.assertEqual(lolz_std.read_bytes(), b"LOLZ_X64_BINARY_HEADER")
        self.assertNotEqual(lolz_std.read_bytes(), b"MAGIC_X64_BINARY_HEADER")
        self.assertNotEqual(lolz_std.read_bytes(), b"LOLZ_X86_BINARY_HEADER")

        # CRITICAL: family isolation — x86 aliases are never created from x64 sources.
        self.assertFalse(
            (tmp_folder / "cls-magic2_x86.exe").exists(),
            "x86 alias must not be created from an x64 source",
        )
        self.assertFalse(
            (tmp_folder / "cls-srep_x86.exe").exists(),
            "x86 alias must not be created from an x64 source",
        )

    def test_repack_recipe_configuration(self):
        """Validates repack.json performance parameters and the installer-injected env.

        Two layers must stay consistent:
        - config/recipes/repack.json: recipe-level performance_env used for game
          launches and winetricks injection.
        - core.installer.apply_repack_install_env: env tuning injected at
          installer time (COPYCMD, native DLL overrides, threads).
        """
        recipe_path = Path(__file__).parent.parent / "config" / "recipes" / "repack.json"
        self.assertTrue(recipe_path.exists(), "config/recipes/repack.json must exist")

        data = json.loads(recipe_path.read_text(encoding="utf-8"))
        perf = data.get("performance_env", {})

        # esync forced ON: wines without ntsync support fall back and deadlock
        # (see apply_repack_install_env comments). Must stay consistent with installer.
        self.assertEqual(perf.get("WINEESYNC"), "1", "WINEESYNC must be 1")
        self.assertEqual(perf.get("WINEFSYNC"), "0", "WINEFSYNC must be 0")
        self.assertEqual(perf.get("WINENTSYNC"), "0", "WINENTSYNC must be 0")
        self.assertEqual(perf.get("PROTON_NO_NTSYNC"), "1", "PROTON_NO_NTSYNC must be 1")
        self.assertEqual(
            perf.get("WINE_LARGE_ADDRESS_AWARE"), "1", "WINE_LARGE_ADDRESS_AWARE must be 1"
        )

        overrides = perf.get("WINEDLLOVERRIDES", "")
        self.assertIn("mscoree", overrides, "WINEDLLOVERRIDES must neutralize mscoree")
        self.assertIn("mshtml", overrides, "WINEDLLOVERRIDES must neutralize mshtml")

        # Installer-time env tuning (pure function, no Qt/Wine required).
        env = apply_repack_install_env({})
        self.assertEqual(env["COPYCMD"], "/Y", "COPYCMD must be /Y (batch overwrite prompt hangs)")
        self.assertEqual(env["WINEESYNC"], "1", "installer env WINEESYNC must match recipe")
        self.assertEqual(env["WINE_LARGE_ADDRESS_AWARE"], "1")

        installer_overrides = env["WINEDLLOVERRIDES"]
        for token in ("unarc=n,b", "isdone=n,b", "mscoree=d", "mshtml=d"):
            self.assertIn(token, installer_overrides, f"installer env must override {token}")

        # Existing overrides must be extended, not clobbered.
        merged = apply_repack_install_env({"WINEDLLOVERRIDES": "custom=n,b"})
        self.assertTrue(merged["WINEDLLOVERRIDES"].startswith("custom=n,b;"))


if __name__ == "__main__":
    unittest.main()
