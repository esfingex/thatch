import locale
import json
from pathlib import Path

# Load dynamic translation databases from local JSON files
STRINGS = {}
LOCALES_DIR = Path(__file__).parent / "locales"

# Auto-detect system language
ACTIVE_LANG = "en"
try:
    system_locale = locale.getdefaultlocale()[0]
    if system_locale and system_locale.startswith("es"):
        ACTIVE_LANG = "es"
except Exception:
    pass


def set_active_lang(lang: str) -> None:
    """Changes the active language at runtime and persists it to DB."""
    global ACTIVE_LANG
    if lang not in ("en", "es"):
        return
    ACTIVE_LANG = lang
    try:
        from database import set_setting

        set_setting("app_language", lang)
    except Exception:
        pass


def load_lang_from_db() -> None:
    """Reads persisted language preference from DB and activates it."""
    global ACTIVE_LANG
    try:
        from database import get_setting

        saved = get_setting("app_language", "")
        if saved in ("en", "es"):
            ACTIVE_LANG = saved
    except Exception:
        pass


def load_locale(lang):
    """Loads a specific locale JSON into the STRINGS cache."""
    if lang in STRINGS:
        return STRINGS[lang]

    locale_file = LOCALES_DIR / f"{lang}.json"
    if locale_file.exists():
        try:
            with open(locale_file, "r", encoding="utf-8") as f:
                STRINGS[lang] = json.load(f)
                return STRINGS[lang]
        except Exception as e:
            print(f"[i18n] Error loading locale resource {lang}: {e}")
    return {}


def _(key, **kwargs):
    """Translates the given key into the active system language."""
    # Ensure active and English fallback locales are loaded
    lang_dict = load_locale(ACTIVE_LANG)
    fallback_dict = load_locale("en")

    text = lang_dict.get(key, fallback_dict.get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text
