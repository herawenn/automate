import sqlite3
import logging

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s',
                    handlers=[logging.FileHandler('files/logs.txt'),
                              logging.StreamHandler()])

def create_tables(conn):
    with conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY,
                    temperature REAL,
                    model TEXT,
                    voice_enabled INTEGER,
                    tone TEXT,
                    output_length TEXT,
                    window_title TEXT,
                    pinned INTEGER,
                    opacity REAL,
                    username TEXT,
                    agent_name TEXT,
                    save_history INTEGER,
                    voice_provider TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY,
                    role TEXT,
                    content TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY,
                    content TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS HelpScript (
                    id INTEGER PRIMARY KEY,
                    content TEXT
                )
            ''')
            conn.commit()
            logging.info("Tables created successfully.")
        except sqlite3.Error as e:
            logging.error(f"Database error creating tables: {e}")
            conn.rollback()
        except Exception as e:
            logging.exception(f"An unexpected error occurred while creating tables: {e}")
            conn.rollback()

def load_settings(conn):
    with conn:
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT * FROM settings WHERE id = 1')
            row = cursor.fetchone()
            if row:
                logging.info("Settings loaded successfully.")
                return {
                    "temperature": row[1],
                    "model": row[2],
                    "voice_enabled": bool(row[3]),
                    "tone": row[4],
                    "output_length": row[5],
                    "window_title": row[6],
                    "pinned": bool(row[7]),
                    "opacity": row[8],
                    "username": row[9],
                    "agent_name": row[10],
                    "save_history": bool(row[11]),
                    "voice_provider": row[12]
                }
            else:
                logging.info("No settings found. Inserting default settings.")
                default_settings = {
                    "temperature": 1.0,
                    "model": 'gemini',
                    "voice_enabled": False,
                    "tone": 'professional',
                    "output_length": 'normal',
                    "window_title": 'Code Companion by PortLords',
                    "pinned": False,
                    "opacity": 0.9,
                    "username": 'User',
                    "agent_name": 'Agent',
                    "save_history": True,
                    "voice_provider": 'free'
                }
                cursor.execute('''
                    INSERT INTO settings (id, temperature, model, voice_enabled, tone, output_length, window_title, pinned, opacity, username, agent_name, save_history, voice_provider)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    1,
                    default_settings["temperature"],
                    default_settings["model"],
                    int(default_settings["voice_enabled"]),
                    default_settings["tone"],
                    default_settings["output_length"],
                    default_settings["window_title"],
                    int(default_settings["pinned"]),
                    default_settings["opacity"],
                    default_settings["username"],
                    default_settings["agent_name"],
                    int(default_settings["save_history"]),
                    default_settings["voice_provider"]
                ))
                conn.commit()
                logging.info("Default settings inserted.")
                return default_settings

        except sqlite3.Error as e:
            logging.error(f"Database error during settings load: {e}")
            return None
        except Exception as e:
            logging.exception(f"An unexpected error occurred during settings load: {e}")
            return None

def save_settings(conn, settings):
    with conn:
        cursor = conn.cursor()
        try:
            logging.debug(f"Saving settings: {settings}")
            cursor.execute('''
                INSERT OR REPLACE INTO settings (id, temperature, model, voice_enabled, tone, output_length, window_title, pinned, opacity, username, agent_name, save_history, voice_provider)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                1,
                settings["temperature"],
                settings["model"],
                int(settings["voice_enabled"]),
                settings["tone"],
                settings["output_length"],
                settings["window_title"],
                int(settings["pinned"]),
                settings["opacity"],
                settings["username"],
                settings["agent_name"],
                int(settings["save_history"]),
                settings["voice_provider"]
            ))
            conn.commit()
            logging.info("Settings saved successfully.")
        except KeyError as e:
            logging.error(f"Missing key in settings dictionary: {e}")
            conn.rollback()
        except sqlite3.Error as e:
            logging.error(f"Database error during settings save: {e}")
            conn.rollback()
        except Exception as e:
            logging.exception(f"An unexpected error occurred during settings save: {e}")
            conn.rollback()

def save_history(conn, history):
    with conn:
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM history')
            for entry in history:
                cursor.execute('INSERT INTO history (role, content) VALUES (?, ?)', (entry['role'], entry['content']))
            conn.commit()
            logging.info("Chat history saved successfully.")
        except sqlite3.Error as e:
            logging.error(f"Database error saving chat history: {e}")
            conn.rollback()
        except Exception as e:
            logging.exception(f"An unexpected error occurred during chat history save: {e}")
            conn.rollback()

def load_history(conn):
    with conn:
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT * FROM history')
            rows = cursor.fetchall()
            return [{"role": row[1], "content": row[2]} for row in rows]
        except sqlite3.Error as e:
            logging.error(f"Database error loading chat history: {e}")
            return []
        except Exception as e:
            logging.exception(f"An unexpected error occurred during chat history load: {e}")
            return []

def load_memories(conn):
    with conn:
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT * FROM memories')
            rows = cursor.fetchall()
            return [row[1] for row in rows]
        except sqlite3.Error as e:
            logging.error(f"Database error loading memories: {e}")
            return []
        except Exception as e:
            logging.exception(f"An unexpected error occurred during memories load: {e}")
            return []

def save_memory(conn, memory):
    with conn:
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO memories (content) VALUES (?)', (memory,))
            conn.commit()
            logging.info(f"Memory '{memory}' saved successfully.")
        except sqlite3.Error as e:
            logging.error(f"Database error saving memory: {e}")
            conn.rollback()
        except Exception as e:
            logging.exception(f"An unexpected error occurred during memory save: {e}")
            conn.rollback()

def remove_memory(conn, memory):
    with conn:
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM memories WHERE content = ?', (memory,))
            conn.commit()
            logging.info(f"Memory '{memory}' removed successfully.")
        except sqlite3.Error as e:
            logging.error(f"Database error removing memory: {e}")
            conn.rollback()
        except Exception as e:
            logging.exception(f"An unexpected error occurred during memory removal: {e}")
            conn.rollback()
