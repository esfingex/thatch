import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

LOCALES_DIR = Path(__file__).resolve().parent.parent / "src" / "locales"


class TestLocales(unittest.TestCase):
    """en.json and es.json must expose exactly the same key set."""

    def test_en_es_key_parity(self):
        en = json.loads((LOCALES_DIR / "en.json").read_text(encoding="utf-8"))
        es = json.loads((LOCALES_DIR / "es.json").read_text(encoding="utf-8"))
        self.assertEqual(set(en), set(es), "en/es locale files must contain identical keys")

    def test_no_empty_values(self):
        for lang in ("en", "es"):
            data = json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))
            empty = [k for k, v in data.items() if not str(v).strip()]
            self.assertEqual(empty, [], f"{lang}.json has empty strings: {empty}")

    def test_fallback_returns_key_for_unknown(self):
        from i18n import _

        self.assertEqual(_("no_such_key_xyz"), "no_such_key_xyz")


if __name__ == "__main__":
    unittest.main()
