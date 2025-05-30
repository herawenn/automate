import os, sys, logging, sqlite3
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_TEST_COMMAND: Optional[str] = None

DbConnection = sqlite3.Connection

class ConnectionError(Exception):
    pass

def connect(db_path: str) -> DbConnection:
    conn: Optional[DbConnection] = None
    try:
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(db_path, check_same_thread=False)
        logger.debug(f"Attempting schema update/creation for database: {db_path}")
        _create_or_update_tables(conn)
        logger.info(f"Successfully connected to database: {db_path}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error at {db_path}: {e}", exc_info=True)
        if conn:
            conn.close()
        raise ConnectionError(f"Database connection failed at {db_path}: {e}") from e
    except Exception as e:
        logger.exception(f"An unexpected error occurred during DB connection or setup at {db_path}: {e}")
        if conn:
            conn.close()
        raise ConnectionError(f"Database initialization failed at {db_path}: {e}") from e

def _create_or_update_tables(conn: DbConnection) -> None:
    try:
        cursor = conn.cursor()

        settings_columns_sql = """
            id INTEGER PRIMARY KEY,
            model_name TEXT,
            temperature REAL,
            admin_mode_enabled INTEGER,
            test_command TEXT
        """
        cursor.execute(f'CREATE TABLE IF NOT EXISTS settings ({settings_columns_sql})')
        conn.commit()

        cursor.execute("PRAGMA table_info(settings)")
        existing_columns: List[str] = [column[1] for column in cursor.fetchall()]

        required_columns: Dict[str, str] = {
             "model_name": "TEXT", "temperature": "REAL",
             "admin_mode_enabled": "INTEGER",
             "test_command": "TEXT"
        }

        if 'chat_mode' in existing_columns:
            logger.info("Schema update: 'chat_mode' column is deprecated and will be ignored if present.")

        for col_name, col_type in required_columns.items():
            if col_name not in existing_columns:
                logger.info(f"Adding missing column '{col_name}' to 'settings' table.")
                cursor.execute(f'ALTER TABLE settings ADD COLUMN {col_name} {col_type}')

                default_value: Any = None
                if col_name == 'admin_mode_enabled': default_value = 0
                elif col_name == 'test_command': default_value = DEFAULT_TEST_COMMAND

                if default_value is not None:
                     cursor.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
                     cursor.execute(f"UPDATE settings SET {col_name} = ? WHERE id = 1 AND {col_name} IS NULL", (default_value,))
                conn.commit()
        
        cursor.execute("DROP TABLE IF EXISTS memories")
        conn.commit()
        logger.debug("Database schema verified/updated successfully.")

    except sqlite3.Error as e:
        logger.error(f"Database error during schema update: {e}", exc_info=True)
        conn.rollback()
        raise
    except Exception as e:
        logger.exception(f"An unexpected error occurred during schema update: {e}")
        conn.rollback()
        raise

def load_settings(conn: DbConnection, default_admin_mode_env_str: Optional[str]) -> Optional[Dict[str, Any]]:
    try:
        cursor = conn.cursor()
        cols_to_select: str = "model_name, temperature, admin_mode_enabled, test_command"
        cursor.execute(f'SELECT {cols_to_select} FROM settings WHERE id = 1')
        row: Optional[Tuple] = cursor.fetchone()

        default_admin_mode = False
        if default_admin_mode_env_str is not None:
            if default_admin_mode_env_str.lower() == 'true':
                default_admin_mode = True
            elif default_admin_mode_env_str.lower() == 'false':
                default_admin_mode = False
            else:
                try:
                    default_admin_mode = bool(int(default_admin_mode_env_str))
                except ValueError:
                    logger.warning(f"Invalid string value for DEFAULT_ADMIN_MODE_ENV ('{default_admin_mode_env_str}'). Defaulting admin mode to False.")

        if row:
            col_names: List[str] = [col.strip() for col in cols_to_select.split(',')]
            settings_dict = dict(zip(col_names, row))

            db_admin_value: Any = settings_dict.get("admin_mode_enabled")
            admin_mode_setting: bool = default_admin_mode
            if db_admin_value is not None:
                try:
                    admin_mode_setting = bool(int(db_admin_value))
                except (ValueError, TypeError):
                    logger.warning(f"Invalid value '{db_admin_value}' for admin_mode_enabled in DB. Using startup default.")
            else:
                admin_mode_setting = default_admin_mode

            loaded_settings: Dict[str, Any] = {
                "model_name": settings_dict.get("model_name") or "gemini",
                "temperature": settings_dict.get("temperature") or 0.25,
                "admin_mode_enabled": admin_mode_setting,
                "test_command": settings_dict.get("test_command"),
            }

            if loaded_settings["test_command"] is None:
                loaded_settings["test_command"] = DEFAULT_TEST_COMMAND

            logger.info("Settings loaded successfully.")
            return loaded_settings
        else:
            logger.info("No settings found (row id=1). Inserting default settings.")
            default_settings_dict: Dict[str, Any] = {
                "model_name": "gemini",
                "temperature": 0.25,
                "admin_mode_enabled": default_admin_mode,
                "test_command": DEFAULT_TEST_COMMAND,
            }
            cols: str = ', '.join(default_settings_dict.keys())
            placeholders: str = ', '.join('?' * len(default_settings_dict))
            
            values_list = []
            for k, v in default_settings_dict.items():
                if isinstance(v, bool): values_list.append(int(v))
                else: values_list.append(v)
            
            values_tuple: Tuple = (1,) + tuple(values_list)

            cursor.execute(f'INSERT INTO settings (id, {cols}) VALUES (?, {placeholders})', values_tuple)
            conn.commit()
            logger.info("Default settings inserted.")
            return default_settings_dict.copy()

    except sqlite3.Error as e:
        logger.error(f"Database error during settings load: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during settings load: {e}")
        return None

def save_settings(conn: DbConnection, settings: Dict[str, Any]) -> None:
    try:
        cursor = conn.cursor()

        admin_mode: bool = bool(settings.get("admin_mode_enabled", False))
        test_cmd: Optional[str] = settings.get("test_command", DEFAULT_TEST_COMMAND)

        if isinstance(test_cmd, str) and not test_cmd.strip():
             test_cmd = None 

        cols_to_save: List[str] = [
             "model_name", "temperature",
             "admin_mode_enabled", "test_command"
        ]
        values_to_save: List[Any] = [
             settings.get("model_name", "gemini"),
             settings.get("temperature", 0.25),
             int(admin_mode),
             test_cmd
        ]

        cols_sql: str = ', '.join(cols_to_save)
        placeholders_sql: str = ', '.join('?' * len(cols_to_save))
        sql: str = f'INSERT OR REPLACE INTO settings (id, {cols_sql}) VALUES (?, {placeholders_sql})'
        values_tuple: Tuple = (1,) + tuple(values_to_save)

        cursor.execute(sql, values_tuple)
        conn.commit()
        logger.info("Settings saved successfully.")

    except sqlite3.Error as e:
        logger.error(f"Database error during settings save: {e}", exc_info=True)
        conn.rollback()
    except Exception as e:
        logger.exception(f"An unexpected error occurred during settings save: {e}")
        conn.rollback()

if __name__ == '__main__':
    _TEST_DIR = os.path.join(os.path.dirname(__file__), 'files')
    _TEST_DB_PATH = os.path.join(_TEST_DIR, 'automate_test.db')

    os.makedirs(_TEST_DIR, exist_ok=True)

    if not logging.getLogger().hasHandlers():
         logging.basicConfig(
             level=logging.DEBUG,
             format='%(asctime)s|%(levelname)s|%(filename)s:%(lineno)d| %(message)s',
             handlers=[logging.StreamHandler(sys.stdout)]
         )
    test_logger = logging.getLogger(__name__)

    test_logger.info(f"Running database.py standalone test. DB: {_TEST_DB_PATH}")

    if os.path.exists(_TEST_DB_PATH):
        test_logger.info(f"Removing existing test database: {_TEST_DB_PATH}")
        try:
            os.remove(_TEST_DB_PATH)
        except OSError as e:
             test_logger.error(f"Failed to remove old test DB: {e}. Proceeding anyway.")

    conn_test: Optional[DbConnection] = None
    try:
        conn_test = connect(_TEST_DB_PATH)
        assert conn_test is not None, "Connection object should not be None"

        test_logger.info("--- Testing Settings ---")
        settings = load_settings(conn_test, default_admin_mode_env_str="false")
        assert settings is not None, "load_settings should return defaults, not None"
        test_logger.debug(f"Initial settings (defaults): {settings}")
        assert 'chat_mode' not in settings, "'chat_mode' should not be in settings"
        assert settings['admin_mode_enabled'] is False, "Default admin_mode_enabled should be False"

        settings['temperature'] = 0.88
        settings['test_command'] = 'pytest --verbose'
        settings['admin_mode_enabled'] = True
        test_logger.debug(f"Saving modified settings: {settings}")
        save_settings(conn_test, settings)

        reloaded = load_settings(conn_test, default_admin_mode_env_str="false")
        assert reloaded is not None, "reload_settings should succeed"
        test_logger.debug(f"Reloaded settings: {reloaded}")
        assert reloaded['temperature'] == 0.88, "Temperature mismatch after reload"
        assert 'chat_mode' not in reloaded, "'chat_mode' should not be in reloaded settings"
        assert reloaded['admin_mode_enabled'] is True, "Admin mode mismatch after reload"
        assert reloaded['test_command'] == 'pytest --verbose', "Test command mismatch"

        test_logger.info("Settings save/load verified.")
        test_logger.info("Memory functions and chat_mode removed, related tests skipped.")
        test_logger.info("Standalone test completed successfully.")

    except Exception as e:
         test_logger.exception(f"Standalone test FAILED: {e}")
         raise
    finally:
        if conn_test:
            try:
                conn_test.close()
                test_logger.info("Test database connection closed.")
            except sqlite3.Error as e:
                 test_logger.error(f"Error closing test DB connection: {e}")
