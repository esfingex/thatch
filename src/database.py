import sqlite3
import json
import shutil
from pathlib import Path


class ThatchDB:
    def __init__(self, db_path: Path | None = None):
        # Resolve base directory relative to this source file (src/database.py)
        self.base_dir = Path(__file__).parent.parent.resolve()

        self.sqlite_path = db_path if db_path else self.base_dir / "thatch_db.sqlite"
        self.json_path = self.base_dir / "thatch_db.json"
        self.recipes_dir = self.base_dir / "config" / "recipes"

        # Ensure default directories exist
        self.default_prefixes_dir = self.base_dir / "prefixes"
        self.default_runners_dir = self.base_dir / "runners"
        self.default_winetricks_cache_dir = Path.home() / ".cache" / "winetricks"

        self.default_prefixes_dir.mkdir(parents=True, exist_ok=True)
        self.default_runners_dir.mkdir(parents=True, exist_ok=True)

        self._games_cache = None
        self._config_cache = None
        self._init_sqlite()
        self._check_and_migrate_json()

    def _init_sqlite(self) -> None:
        """Initializes the SQLite database tables."""
        conn = sqlite3.connect(self.sqlite_path)
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

        conn.commit()
        conn.close()

    def _check_and_migrate_json(self) -> None:
        """Migrates data from thatch_db.json if sqlite is empty but json exists."""
        if not self.json_path.exists():
            self._set_default_configs()
            return

        # Check if we already have games in SQLite
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM games")
        game_count = cursor.fetchone()[0]
        conn.close()

        if game_count > 0:
            return  # already migrated

        # Perform migration
        try:
            print(f"[DB SQLite] Migrating legacy {self.json_path.name} to SQLite...")
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            conn = sqlite3.connect(self.sqlite_path)
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

            conn.commit()
            conn.close()

            # Backup old JSON file
            backup_path = self.json_path.with_suffix(".json.bak")
            shutil.move(str(self.json_path), str(backup_path))
            print(
                f"[DB SQLite] Migration complete. Legacy JSON backed up to {backup_path.name}."
            )
        except Exception as e:
            print(f"[DB SQLite] Error migrating legacy JSON: {e}")
            self._set_default_configs()

    def _set_default_configs(self) -> None:
        conn = sqlite3.connect(self.sqlite_path)
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
        conn.commit()
        conn.close()

    def _get_config_val(self, key: str, default: str = "") -> str:
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM global_config WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default

    def _set_config_val(self, key: str, value: str) -> None:
        self._config_cache = None  # invalidate cache
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO global_config (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
        conn.commit()
        conn.close()

    @property
    def data(self) -> dict:
        """Returns a dict representation of the database for compatibility."""
        if self._games_cache is None or self._config_cache is None:
            self._load_caches()
        return {"global_config": self._config_cache, "games": self._games_cache}

    def _load_caches(self) -> None:
        conn = sqlite3.connect(self.sqlite_path)
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
        conn.close()

    def save(self) -> None:
        """Commits cache changes to the SQLite database."""
        if self._games_cache is None and self._config_cache is None:
            return

        conn = sqlite3.connect(self.sqlite_path)
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
        conn.commit()
        conn.close()

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

    def load_recipes(self) -> dict[str, dict[str, any]]:
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

    # ─── Games Library Actions ───────────────────────────────────────────────

    def list_games(self) -> dict[str, dict[str, any]]:
        return self.data["games"]

    def get_game(self, name: str) -> dict[str, any] | None:
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
        conn = sqlite3.connect(self.sqlite_path)
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
        conn.commit()
        conn.close()

    def remove_game(self, name: str) -> None:
        self._games_cache = None  # invalidate cache
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM games WHERE name = ?", (name,))
        conn.commit()
        conn.close()

    # ─── Winetricks Catalog Actions ─────────────────────────────────────────

    def get_winetricks_catalog(self) -> list[dict]:
        """Loads cached winetricks catalog from SQLite database."""
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute("SELECT verb, name, desc, type FROM winetricks_catalog")
        rows = cursor.fetchall()
        conn.close()
        return [{"verb": r[0], "name": r[1], "desc": r[2], "type": r[3]} for r in rows]

    def save_winetricks_catalog(self, catalog: list[dict]) -> None:
        """Saves/updates winetricks catalog into SQLite database."""
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()

        for entry in catalog:
            cursor.execute(
                """
                INSERT OR REPLACE INTO winetricks_catalog (verb, name, desc, type, last_updated)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (entry["verb"], entry["name"], entry["desc"], entry["type"]),
            )

        conn.commit()
        conn.close()


def get_setting(key: str, default: str = "") -> str:
    """Reads a setting value from the global_config table in the default database."""
    db = ThatchDB()
    return db._get_config_val(key, default)


def set_setting(key: str, value: str) -> None:
    """Saves or updates a setting value in the global_config table."""
    db = ThatchDB()
    db._set_config_val(key, value)
