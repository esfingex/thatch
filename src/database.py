import sqlite3
import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class ThatchDB:
    def __init__(self, db_path: Path | None = None):
        # Resolve base directory relative to this source file (src/database.py)
        self.base_dir = Path(__file__).parent.parent.resolve()

        # User data directory (~/thatch)
        self.user_data_dir = Path.home() / "thatch"
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        # Database path (default to ~/thatch/thatch_db.sqlite unless specified or legacy exists)
        legacy_db = self.base_dir / "thatch_db.sqlite"
        old_local_db = Path.home() / ".local" / "share" / "thatch" / "thatch_db.sqlite"
        user_db = self.user_data_dir / "thatch_db.sqlite"

        if db_path:
            self.sqlite_path = db_path
        elif user_db.exists():
            self.sqlite_path = user_db
        elif old_local_db.exists():
            try:
                shutil.copy2(old_local_db, user_db)
                self.sqlite_path = user_db
            except Exception:
                self.sqlite_path = old_local_db
        elif legacy_db.exists():
            try:
                shutil.copy2(legacy_db, user_db)
                self.sqlite_path = user_db
            except Exception:
                self.sqlite_path = legacy_db
        else:
            self.sqlite_path = user_db

        self.json_path = self.base_dir / "thatch_db.json"
        self.recipes_dir = self.base_dir / "config" / "recipes"

        # Default storage directories in ~/thatch
        self.default_prefixes_dir = self.user_data_dir / "prefixes"
        self.default_runners_dir = self.user_data_dir / "runners"
        self.default_winetricks_cache_dir = Path.home() / ".cache" / "winetricks"

        self.default_prefixes_dir.mkdir(parents=True, exist_ok=True)
        self.default_runners_dir.mkdir(parents=True, exist_ok=True)

        # Automatically migrate legacy prefixes from .local/share if present
        old_local_prefixes = Path.home() / ".local" / "share" / "thatch" / "prefixes"
        if old_local_prefixes.exists() and old_local_prefixes != self.default_prefixes_dir:
            for p in old_local_prefixes.iterdir():
                if p.is_dir():
                    target = self.default_prefixes_dir / p.name
                    if not target.exists():
                        try:
                            shutil.move(str(p), str(target))
                        except Exception as e:
                            print(f"[DB] Migration warning for prefix {p.name}: {e}")
                    else:
                        # Never destroy user data: a name collision with an
                        # existing migrated prefix is preserved side-by-side.
                        conflict = self.default_prefixes_dir / f"{p.name}_migrated_conflict"
                        suffix = 1
                        while conflict.exists():
                            conflict = (
                                self.default_prefixes_dir / f"{p.name}_migrated_conflict_{suffix}"
                            )
                            suffix += 1
                        try:
                            shutil.move(str(p), str(conflict))
                        except Exception as e:
                            print(f"[DB] Migration warning for prefix {p.name}: {e}")

        self._games_cache = None
        self._config_cache = None
        self._init_sqlite()
        self._check_and_migrate_json()

    @contextmanager
    def _db(self):
        """Yields a sqlite3 connection with guaranteed commit-on-success and
        close-always semantics, so an exception can never leave the database
        locked or the connection dangling."""
        conn = sqlite3.connect(self.sqlite_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_sqlite(self) -> None:
        """Initializes the SQLite database tables."""
        with self._db() as conn:
            # WAL: readers never block the writer and a crashed process cannot
            # corrupt the last committed transaction.
            conn.execute("PRAGMA journal_mode=WAL")
            cursor = conn.cursor()

            # 1. Config Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS global_config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # 2. Games Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    name TEXT PRIMARY KEY,
                    exe TEXT,
                    prefix TEXT,
                    runner TEXT,
                    recipe_id TEXT,
                    virtual_desktop INTEGER DEFAULT 0,
                    virtual_desktop_res TEXT DEFAULT '1920x1080',
                    dpi_scale INTEGER DEFAULT 96,
                    target_monitor TEXT DEFAULT 'default',
                    sandbox INTEGER DEFAULT 0
                )
            """)

            # Schema migration: Check if target_monitor and sandbox exist in games table
            cursor.execute("PRAGMA table_info(games)")
            columns = [row[1] for row in cursor.fetchall()]
            if "target_monitor" not in columns:
                try:
                    cursor.execute(
                        "ALTER TABLE games ADD COLUMN target_monitor TEXT DEFAULT 'default'"
                    )
                except Exception as e:
                    print(f"[DB SQLite Migration] Failed to add target_monitor column: {e}")
            if "sandbox" not in columns:
                try:
                    cursor.execute("ALTER TABLE games ADD COLUMN sandbox INTEGER DEFAULT 0")
                except Exception as e:
                    print(f"[DB SQLite Migration] Failed to add sandbox column: {e}")

            # 3. Winetricks Catalog Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS winetricks_catalog (
                    verb TEXT PRIMARY KEY,
                    name TEXT,
                    desc TEXT,
                    type TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def _check_and_migrate_json(self) -> None:
        """Migrates data from thatch_db.json if sqlite is empty but json exists."""
        if not self.json_path.exists():
            self._set_default_configs()
            return

        # Check if we already have games in SQLite
        with self._db() as conn:
            game_count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

        if game_count > 0:
            return  # already migrated

        # Perform migration
        try:
            print(f"[DB SQLite] Migrating legacy {self.json_path.name} to SQLite...")
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            with self._db() as conn:
                cursor = conn.cursor()

                # Migrate config
                config = data.get("global_config", {})
                for k, v in config.items():
                    cursor.execute(
                        "INSERT OR REPLACE INTO global_config (key, value) VALUES (?, ?)",
                        (k, str(v)),
                    )

                # Migrate games
                games = data.get("games", {})
                for gname, ginfo in games.items():
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO games (
                            name, exe, prefix, runner, recipe_id,
                            virtual_desktop, virtual_desktop_res, dpi_scale
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            gname,
                            ginfo.get("exe", ""),
                            ginfo.get("prefix", "").strip().replace(" ", "_"),
                            ginfo.get("runner", ""),
                            ginfo.get("recipe_id", "default_gaming"),
                            1 if ginfo.get("virtual_desktop", False) else 0,
                            ginfo.get("virtual_desktop_res", "1920x1080"),
                            ginfo.get("dpi_scale", 96),
                        ),
                    )

            # Backup old JSON file
            backup_path = self.json_path.with_suffix(".json.bak")
            shutil.move(str(self.json_path), str(backup_path))
            print(f"[DB SQLite] Migration complete. Legacy JSON backed up to {backup_path.name}.")
        except Exception as e:
            print(f"[DB SQLite] Error migrating legacy JSON: {e}")
            self._set_default_configs()

    def _set_default_configs(self) -> None:
        with self._db() as conn:
            cursor = conn.cursor()
            defaults = {
                "prefixes_dir": str(self.default_prefixes_dir),
                "runners_dir": str(self.default_runners_dir),
                "winetricks_cache_dir": str(self.default_winetricks_cache_dir),
                "launch_mode": "keep",
            }
            for k, v in defaults.items():
                cursor.execute(
                    "INSERT OR IGNORE INTO global_config (key, value) VALUES (?, ?)", (k, v)
                )

    def _get_config_val(self, key: str, default: str = "") -> str:
        with self._db() as conn:
            row = conn.execute("SELECT value FROM global_config WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def _set_config_val(self, key: str, value: str) -> None:
        self._config_cache = None  # invalidate cache
        with self._db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO global_config (key, value) VALUES (?, ?)",
                (key, str(value)),
            )

    @property
    def data(self) -> dict:
        """Returns a dict representation of the database for compatibility."""
        if self._games_cache is None or self._config_cache is None:
            self._load_caches()
        return {"global_config": self._config_cache, "games": self._games_cache}

    def _load_caches(self) -> None:
        with self._db() as conn:
            cursor = conn.cursor()

            # Load config
            cursor.execute("SELECT key, value FROM global_config")
            self._config_cache = {row[0]: row[1] for row in cursor.fetchall()}

            # Load games
            cursor.execute(
                "SELECT name, exe, prefix, runner, recipe_id, virtual_desktop, virtual_desktop_res, dpi_scale, target_monitor, sandbox FROM games"
            )
            self._games_cache = {}
            for row in cursor.fetchall():
                self._games_cache[row[0]] = {
                    "exe": row[1],
                    "prefix": row[2],
                    "runner": row[3],
                    "recipe_id": row[4],
                    "virtual_desktop": bool(row[5]),
                    "virtual_desktop_res": row[6],
                    "dpi_scale": row[7],
                    "target_monitor": row[8] if row[8] else "default",
                    "sandbox": bool(row[9]),
                }

    def save(self) -> None:
        """Commits cache changes to the SQLite database."""
        if self._games_cache is None and self._config_cache is None:
            return

        with self._db() as conn:
            cursor = conn.cursor()

            # 1. Save config
            if self._config_cache is not None:
                for k, v in self._config_cache.items():
                    cursor.execute(
                        "INSERT OR REPLACE INTO global_config (key, value) VALUES (?, ?)",
                        (k, str(v)),
                    )

            # 2. Save games
            if self._games_cache is not None:
                # First, delete games that were removed from cache
                cursor.execute("SELECT name FROM games")
                existing_names = [row[0] for row in cursor.fetchall()]
                for name in existing_names:
                    if name not in self._games_cache:
                        cursor.execute("DELETE FROM games WHERE name = ?", (name,))

                # Insert or replace all cache games
                for name, ginfo in self._games_cache.items():
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO games (
                            name, exe, prefix, runner, recipe_id, 
                            virtual_desktop, virtual_desktop_res, dpi_scale, target_monitor, sandbox
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            name,
                            ginfo.get("exe"),
                            ginfo.get("prefix"),
                            ginfo.get("runner"),
                            ginfo.get("recipe_id", "default_gaming"),
                            1 if ginfo.get("virtual_desktop") else 0,
                            ginfo.get("virtual_desktop_res", "1920x1080"),
                            ginfo.get("dpi_scale", 96),
                            ginfo.get("target_monitor", "default"),
                            1 if ginfo.get("sandbox") else 0,
                        ),
                    )

    # ─── Global Configuration Actions ─────────────────────────────────────────

    def get_prefixes_dir(self) -> Path:
        path_str = self._get_config_val("prefixes_dir", str(self.default_prefixes_dir))
        p = Path(path_str)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def set_prefixes_dir(self, path: Path | str) -> None:
        self._set_config_val("prefixes_dir", str(Path(path).resolve()))

    def get_runners_dir(self) -> Path:
        path_str = self._get_config_val("runners_dir", str(self.default_runners_dir))
        p = Path(path_str)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def set_runners_dir(self, path: Path | str) -> None:
        self._set_config_val("runners_dir", str(Path(path).resolve()))

    def get_winetricks_cache_dir(self) -> Path:
        path_str = self._get_config_val(
            "winetricks_cache_dir", str(self.default_winetricks_cache_dir)
        )
        p = Path(path_str)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def set_winetricks_cache_dir(self, path: Path | str) -> None:
        self._set_config_val("winetricks_cache_dir", str(Path(path).resolve()))

    def get_launch_mode(self) -> str:
        return self._get_config_val("launch_mode", "keep")

    def set_launch_mode(self, mode: str) -> None:
        if mode in ["extreme", "stealth", "keep"]:
            self._set_config_val("launch_mode", mode)

    # ─── Isolated Recipes Directory Parser ───────────────────────────────────

    def load_recipes(self) -> dict[str, dict[str, Any]]:
        """Dynamically scans config/recipes/*.json and builds the recipes index."""
        recipes = {}
        self.recipes_dir.mkdir(parents=True, exist_ok=True)

        for json_path in self.recipes_dir.glob("*.json"):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    recipe_data = json.load(f)
                    recipe_id = json_path.stem
                    recipe_data["recipe_id"] = recipe_id
                    recipes[recipe_id] = recipe_data
            except Exception as e:
                print(f"[DB] Error loading recipe {json_path.name}: {e}")

        if not recipes:
            recipes["default_gaming"] = {
                "recipe_id": "default_gaming",
                "display_name": "Juego Genérico (Estándar)",
                "required_verbs": [],
                "recommended_runner": "wine-cachyos",
                "performance_env": {"WINEESYNC": "1", "WINEMFSYNC": "1"},
                "description": "Configuración estándar.",
            }

        return recipes

    # ─── Prefix Directories Lookup ───────────────────────────────────────────

    def list_existing_prefixes(self) -> list[str]:
        """Lists folders inside get_prefixes_dir() to enable prefix sharing."""
        p_dir = self.get_prefixes_dir()
        if not p_dir.exists():
            return []
        return sorted(
            [
                entry.name
                for entry in p_dir.iterdir()
                if entry.is_dir()
                and not entry.name.startswith(".")
                and entry.name != "temp_zeus_prefix"
            ]
        )

    def rename_prefix(self, old_name: str, new_name: str) -> bool:
        """Renames an existing chest WINEPREFIX folder and updates all referencing game records."""
        if not old_name or not new_name or old_name == new_name:
            return False

        clean_new = new_name.strip().replace(" ", "_")
        p_dir = self.get_prefixes_dir()
        old_path = p_dir / old_name
        new_path = p_dir / clean_new

        if not old_path.exists() or new_path.exists():
            return False

        try:
            old_path.rename(new_path)
        except Exception as e:
            print(f"[DB] Error renaming prefix folder from '{old_name}' to '{clean_new}': {e}")
            return False

        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE games SET prefix = ? WHERE prefix = ?", (clean_new, old_name))

        if self._games_cache:
            for ginfo in self._games_cache.values():
                if ginfo.get("prefix") == old_name:
                    ginfo["prefix"] = clean_new

        return True

    # ─── Games Library Actions ───────────────────────────────────────────────

    def list_games(self) -> dict[str, dict[str, Any]]:
        return self.data["games"]

    def get_game(self, name: str) -> dict[str, Any] | None:
        return self.list_games().get(name)

    def add_game(
        self,
        name: str,
        exe: str,
        runner: str,
        prefix: str,
        recipe_id: str = "default_gaming",
    ) -> None:
        self._games_cache = None  # invalidate cache
        with self._db() as conn:
            cursor = conn.cursor()

            # Check if game already exists to preserve custom settings like virtual_desktop / dpi_scale / target_monitor / sandbox
            cursor.execute(
                "SELECT virtual_desktop, virtual_desktop_res, dpi_scale, target_monitor, sandbox FROM games WHERE name = ?",
                (name,),
            )
            row = cursor.fetchone()

            vd = row[0] if row else 0
            vd_res = row[1] if row else "1920x1080"
            dpi = row[2] if row else 96
            monitor = row[3] if row else "default"
            sndbox = row[4] if row else 0

            cursor.execute(
                """
                INSERT OR REPLACE INTO games (
                    name, exe, prefix, runner, recipe_id, 
                    virtual_desktop, virtual_desktop_res, dpi_scale, target_monitor, sandbox
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    name,
                    str(Path(exe).resolve()),
                    prefix.strip().replace(" ", "_"),
                    runner,
                    recipe_id,
                    vd,
                    vd_res,
                    dpi,
                    monitor,
                    sndbox,
                ),
            )

    def remove_game(self, name: str) -> None:
        self._games_cache = None  # invalidate cache
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM games WHERE name = ?", (name,))

    # ─── Winetricks Catalog Actions ─────────────────────────────────────────

    def get_winetricks_catalog(self) -> list[dict]:
        """Loads cached winetricks catalog from SQLite database."""
        with self._db() as conn:
            rows = conn.execute("SELECT verb, name, desc, type FROM winetricks_catalog").fetchall()
        return [{"verb": r[0], "name": r[1], "desc": r[2], "type": r[3]} for r in rows]

    def save_winetricks_catalog(self, catalog: list[dict]) -> None:
        """Saves/updates winetricks catalog into SQLite database."""
        with self._db() as conn:
            for entry in catalog:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO winetricks_catalog (verb, name, desc, type, last_updated)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                    (entry["verb"], entry["name"], entry["desc"], entry["type"]),
                )


# ── Module-level lazy singleton — avoids re-opening SQLite on every i18n call ──
_db_singleton: "ThatchDB | None" = None


def _get_singleton() -> "ThatchDB":
    """Returns the shared ThatchDB singleton, creating it on first call."""
    global _db_singleton
    if _db_singleton is None:
        _db_singleton = ThatchDB()
    return _db_singleton


def get_setting(key: str, default: str = "") -> str:
    """Reads a setting value from the global_config table using the shared DB singleton."""
    return _get_singleton()._get_config_val(key, default)


def set_setting(key: str, value: str) -> None:
    """Saves or updates a setting value in the global_config table using the shared DB singleton."""
    _get_singleton()._set_config_val(key, value)
