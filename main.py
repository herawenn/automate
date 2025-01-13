import os
import sys
import time
import mimetypes
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
import google.generativeai as genai
from tqdm import tqdm
from colorama import Fore, Style, init
import ctypes, win32gui, win32con, platform, psutil
from dotenv import load_dotenv
import helper, database, voice
from mistralai import Mistral

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'files', '.env'))

init()
R = Fore.RED
Y = Fore.YELLOW
X = Fore.RESET

if platform.system() == 'Windows':
    os.system("mode con cols=85 lines=25")

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s',
                    handlers=[RotatingFileHandler('files/logs.txt', maxBytes=1000000, backupCount=1),
                              logging.StreamHandler()])

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, 'files', os.getenv('DB_PATH', 'db.db'))
PROJECT_DIRECTORY = os.path.join(PROJECT_ROOT, os.getenv('PROJECT_DIRECTORY', 'ProjectDir'))

conn = sqlite3.connect(DB_PATH)
database.create_tables(conn)

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')

genai.configure(api_key=GEMINI_API_KEY)
mistral = Mistral(api_key=MISTRAL_API_KEY)

generation_config = {
    "temperature": 0.8,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 200,
    "response_mime_type": "text/plain",
}

safety_settings = {
    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
    "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
    "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-pro",
    generation_config=generation_config,
    safety_settings=safety_settings,
)

chat_session = model.start_chat(history=[])

system_prompt = """
Your responses should be clear, concise, and professional. Treat me as an expert, use technical jargon. No introductions or conclusions. Do not offer unsolicited information to the user.
I will specify Developer mode (dev=on/off). When in developer mode, do not attempt the normal conversational flow. Make the requested changes without any explanation or discussion. If a minor change was made, only print the code in question. If a major change was made, print the full code.
"""

current_model = "gemini"
history = []
voice_enabled = False
voice_provider = "windows" if not ELEVENLABS_API_KEY else "elevenlabs"
tone = "professional"
output_length = "low"
window_title = "Code Companion by PortLords"
pinned = False
opacity = 0.9
username = "User"
agent_name = "Agent"
save_history = True

OUTPUT_LENGTH_OPTIONS = {
    "low": 200,
    "normal": 500,
    "high": 1000
}

TONE_OPTIONS = ["casual", "formal", "professional"]

def show_settings():
    try:
        os.system("mode con cols=90 lines=30")
        os.system('cls')
        print(f"  __   ___ ___ ___         __   __\n /__  |__   |   |  | |\\ | / _  /__\n  __/ |___  |   |  | | \\| \\__>  __/")
        print('')
        print(f" Window: {Y}{window_title}{X}")
        print(f" Username: {Y}{username}{X}")
        print(f" Agent: {Y}{agent_name}{X}")
        print(f" Model: {Y}{current_model}{X}")
        print('')
        print(f" Voice: {Y}{'Enabled' if voice_enabled else 'Disabled'}{X}")
        print(f" Provider: {Y}{voice_provider}{X}")
        print(f" Temp: {Y}{generation_config['temperature']}{X}")
        print(f" Tone: {Y}{tone}{X}")
        print(f" Opacity: {Y}{opacity}{X}")
        print(f" Output: {Y}{output_length}{X}")
        print('')
        print(f" Pinned: {Y}{'Yes' if pinned else 'No'}{X}")
        print(f" History: {Y}{'Yes' if save_history else 'No'}{X}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

def load_settings():
    try:
        global generation_config, current_model, voice_enabled, tone, output_length, window_title, pinned, opacity, username, agent_name, save_history, voice_provider
        settings = database.load_settings(conn)
        if settings:
            generation_config["temperature"] = settings["temperature"]
            current_model = settings["model"]
            tone = settings["tone"]
            output_length = settings["output_length"]
            voice_enabled = settings["voice_enabled"]
            voice_provider = settings.get("voice_provider", "windows")
            window_title = settings.get("window_title", "Code Companion by PortLords")
            pinned = settings.get("pinned", False)
            opacity = settings.get("opacity", 0.9)
            username = settings.get("username", "User")
            agent_name = settings.get("agent_name", "Agent")
            save_history = settings.get("save_history", True)
        else:
            logging.warning("No settings loaded from database. Using defaults.")

    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

def save_settings(conn, settings):
    cursor = conn.cursor()
    try:
        logging.debug(f"Attempting to save settings: {settings}")
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

def save_history(history):
    try:
        if save_history:
            database.save_history(conn, history)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

def load_history():
    try:
        return database.load_history(conn)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return []

def clear_screen():
    try:
        os.system('cls')
        memories_count = len(database.load_memories(conn))
        files_count = len([f for f in os.listdir(PROJECT_DIRECTORY) if os.path.isfile(os.path.join(PROJECT_DIRECTORY, f))])

        print(f"\n\n\t\t\t       Type '{Y}/commands{X}' for commands, or '{Y}/exit{X}' to quit\n\n")
        print(f"\t\t\t\t\t   Memories: {Y}{memories_count}{X} Files in: {Y}{os.path.basename(PROJECT_DIRECTORY)}{X}: [{Y}{files_count}{X}]")
        print(f"\n\n\t\t\t\t\t\t\t   From {Y}PortLords{X} w Love\n\n\n\n")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

def show_commands():
    try:
        os.system("mode con cols=90 lines=38")
        os.system('cls')
        print(f"""       ___       __            ___\n |__| |__  |    |__)     |\\/| |__  |\\ | |  |\n |  | |___ |___ |        |  | |___ | \\| \\__/""")
        print(f"\n Configuration{Y}:{X}\n")
        print(f" {Y}/username{X} <name>: Change the username")
        print(f" {Y}/agent{X} <name>: Change the agent's name")
        print(f" {Y}/title{X} <title>: Change the window title")
        print(f" {Y}/opacity{X} <value>: Change the window opacity")
        print(f" {Y}/temp{X} <value>: Change the temperature")
        print(f" {Y}/tone{X} <casual/formal/professional>: Change the tone of responses")
        print(f" {Y}/output{X} <low/normal/high>: Change the output length")
        print(f" {Y}/provider{X} <elevenlabs/windows>: Change voice provider")
        print("")
        print(f" Interaction{Y}:{X}\n")
        print(f" {Y}/pin{X}: Pin to top")
        print(f" {Y}/commands{X}: Show available commands")
        print(f" {Y}/settings{X}: Show the user settings")
        print(f" {Y}/clear{X}: Clear the console")
        print(f" {Y}/voice{X} <on/off>: Toggle voice mode")
        print(f" {Y}/check{X} <filename>: Discuss a file with AI")
        print(f" {Y}/improve{X} <filename>: Improve a file")
        print(f" {Y}/exit{X}: Exit the application")
        print("")
        print(f" Management{Y}:{X}\n")
        print(f" {Y}/specs{X}: Show system specifications")
        print(f" {Y}/save_history{X} <on/off>: Toggle saving conversation history")
        print(f" {Y}/rmhistory{X}: Delete conversation history")
        print(f" {Y}/memories{X} <add/remove/display> <memory>: Manage memories")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

def show_specs():
    try:
        os.system('cls')
        print("\nSystem Specifications:\n")
        print(f"  Device: {Y}{platform.node()}{X}  Username: {Y}{os.getlogin()}{X}")

        # CPU information
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count(logical=True)
        print(f"\n  CPU: {Y}{cpu_percent:.1f}%{X} usage {Y}({cpu_count}{X} cores)")

        # Memory information
        mem = psutil.virtual_memory()
        print(f"  Memory: {Y}{mem.percent}%{X} usage {Y}({psutil.virtual_memory().total / (1024**3):.1f}GB{X} total, {Y}{psutil.virtual_memory().available / (1024**3):.1f}GB{X} available)")

        # Disk information
        disk = psutil.disk_usage('/')
        print(f"  Disk: {Y}{disk.percent}%{X} usage {Y}({disk.total / (1024**3):.1f}GB{X} total, {Y}{disk.free / (1024**3):.1f}GB{X} free)")

        print("\n")
    except Exception as e:
        logging.error(f"An unexpected error occurred while getting system specs: {e}")

def set_window_attributes():
    try:
        hwnd = win32gui.GetForegroundWindow()
        win32gui.SetWindowText(hwnd, window_title)
        if pinned:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetLayeredWindowAttributes(hwnd, 0, int(opacity * 255), win32con.LWA_ALPHA)
    except Exception as e:
        logging.error(f"An unexpected error occurred setting window attributes: {e}")

def display_progress(message):
    sys.stdout.write(f"\r{message}")
    sys.stdout.flush()

def main():
    try:
        global generation_config, current_model, history, voice_enabled, tone, output_length, window_title, pinned, opacity, username, agent_name, save_history, voice_provider, mistral, chat_session, model

        clear_screen()
        set_window_attributes()

        while True:
            print("")

            user_message = input(f" {Y}{username}:{X} ")

            if user_message.startswith('/'):
                parts = user_message.split()
                command = parts[0][1:]
                params = parts[1:]

                if command == "settings":
                    show_settings()
                elif command == "commands":
                    show_commands()
                elif command == "clear":
                    clear_screen()
                elif command == "specs":
                    show_specs()
                elif command == "exit":
                    save_history(history)
                    break

                elif command == "check":
                    try:
                        filepath = params[0]
                        if not os.path.exists(filepath):
                            raise FileNotFoundError(f"Error: File '{filepath}' not found.")
                        if not os.path.isfile(filepath):
                            raise ValueError(f"Error: '{filepath}' is not a file.")

                        with open(filepath, 'r') as f:
                            file_content = f.read()

                        agent_message = helper.chat_with_model(file_content, model_name=current_model, chat_session=chat_session, mistral_instance=mistral)

                        print(f"{R}{agent_name}:{X} {agent_message}")

                    except (FileNotFoundError, ValueError) as e:
                        print(f"{R}Error: {e}{X}")
                    except Exception as e:
                        logging.exception(f"An unexpected error occurred during file check: {e}")

                elif command == "username":
                    username = params[0]
                    settings_to_save = {"username": username, "temperature": generation_config["temperature"], "model": current_model, "voice_enabled": voice_enabled, "tone": tone, "output_length": output_length, "window_title": window_title, "pinned": pinned, "opacity": opacity, "agent_name": agent_name, "save_history": save_history, "voice_provider": voice_provider}
                    save_settings(conn, settings_to_save)
                    print(f"\n [{Y}+{X}] username updated to: {Y}{username}{X}")

                elif command == "agent":
                    agent_name = params[0]
                    settings_to_save = {"username": username, "temperature": generation_config["temperature"], "model": current_model, "voice_enabled": voice_enabled, "tone": tone, "output_length": output_length, "window_title": window_title, "pinned": pinned, "opacity": opacity, "agent_name": agent_name, "save_history": save_history, "voice_provider": voice_provider}
                    save_settings(conn, settings_to_save)
                    print(f"\n [{Y}+{X}] agent name updated to: {Y}{agent_name}{X}")

                elif command == "voice":
                    if params[0].lower() == "on":
                        voice_enabled = True
                    elif params[0].lower() == "off":
                        voice_enabled = False
                    else:
                        print(f"{R}Invalid status. Please use 'on' or 'off'.{X}")
                    settings_to_save = {"username": username, "temperature": generation_config["temperature"], "model": current_model, "voice_enabled": voice_enabled, "tone": tone, "output_length": output_length, "window_title": window_title, "pinned": pinned, "opacity": opacity, "agent_name": agent_name, "save_history": save_history, "voice_provider": voice_provider}
                    save_settings(conn, settings_to_save)
                    print(f"\n [{Y}+{X}] Voice {'enabled' if voice_enabled else 'disabled'}.{X}")

                elif command == "provider":
                    voice_provider = params[0].lower()
                    if voice_provider not in ["elevenlabs", "windows"]:
                        print(f"{R}Invalid voice provider. Please use 'elevenlabs' or 'windows'.{X}")
                    else:
                        settings_to_save = {"username": username, "temperature": generation_config["temperature"], "model": current_model, "voice_enabled": voice_enabled, "tone": tone, "output_length": output_length, "window_title": window_title, "pinned": pinned, "opacity": opacity, "agent_name": agent_name, "save_history": save_history, "voice_provider": voice_provider}
                        save_settings(conn, settings_to_save)
                        print(f"\n [{Y}+{X}] Voice provider updated to: {Y}{voice_provider}{X}")

                elif command == "temp":
                    try:
                        generation_config["temperature"] = float(params[0])
                        settings_to_save = {"username": username, "temperature": generation_config["temperature"], "model": current_model, "voice_enabled": voice_enabled, "tone": tone, "output_length": output_length, "window_title": window_title, "pinned": pinned, "opacity": opacity, "agent_name": agent_name, "save_history": save_history, "voice_provider": voice_provider}
                        save_settings(conn, settings_to_save)
                        print(f"\n [{Y}+{X}] Temperature updated to: {Y}{generation_config['temperature']}{X}")
                    except ValueError:
                        print(f"{R}Invalid temperature value.{X}")

                elif command == "tone":
                    tone = params[0].lower()
                    if tone not in TONE_OPTIONS:
                        print(f"{R}Invalid tone. Please use 'casual', 'formal', or 'professional'.{X}")
                    else:
                        settings_to_save = {"username": username, "temperature": generation_config["temperature"], "model": current_model, "voice_enabled": voice_enabled, "tone": tone, "output_length": output_length, "window_title": window_title, "pinned": pinned, "opacity": opacity, "agent_name": agent_name, "save_history": save_history, "voice_provider": voice_provider}
                        save_settings(conn, settings_to_save)
                        print(f"\n [{Y}+{X}] Tone updated to: {Y}{tone}{X}")

                elif command == "output":
                    output_length = params[0].lower()
                    if output_length not in OUTPUT_LENGTH_OPTIONS:
                        print(f"{R}Invalid output length. Please use 'low', 'normal', or 'high'.{X}")
                    else:
                        generation_config["max_output_tokens"] = OUTPUT_LENGTH_OPTIONS[output_length]
                        settings_to_save = {"username": username, "temperature": generation_config["temperature"], "model": current_model, "voice_enabled": voice_enabled, "tone": tone, "output_length": output_length, "window_title": window_title, "pinned": pinned, "opacity": opacity, "agent_name": agent_name, "save_history": save_history, "voice_provider": voice_provider}
                        save_settings(conn, settings_to_save)
                        print(f"\n [{Y}+{X}] Output length updated to: {Y}{output_length}{X}")

                elif command == "title":
                    window_title = params[0]
                    settings_to_save = {"username": username, "temperature": generation_config["temperature"], "model": current_model, "voice_enabled": voice_enabled, "tone": tone, "output_length": output_length, "window_title": window_title, "pinned": pinned, "opacity": opacity, "agent_name": agent_name, "save_history": save_history, "voice_provider": voice_provider}
                    save_settings(conn, settings_to_save)
                    print(f"\n [{Y}+{X}] Window title updated to: {Y}{window_title}{X}")
                    set_window_attributes()

                elif command == "pin":
                    pinned = not pinned
                    settings_to_save = {"username": username, "temperature": generation_config["temperature"], "model": current_model, "voice_enabled": voice_enabled, "tone": tone, "output_length": output_length, "window_title": window_title, "pinned": pinned, "opacity": opacity, "agent_name": agent_name, "save_history": save_history, "voice_provider": voice_provider}
                    save_settings(conn, settings_to_save)
                    print(f"\n [{Y}+{X}] Pinned: {'Yes' if pinned else 'No'}{X}")
                    set_window_attributes()

                elif command == "improve":
                    try:
                        filepath = os.path.join(PROJECT_DIRECTORY, params[0])
                        if not os.path.exists(filepath):
                            raise FileNotFoundError(f"Error: File '{filepath}' not found.")
                        if not os.path.isfile(filepath):
                            raise ValueError(f"Error: '{filepath}' is not a file.")

                        success, error_message = helper.improve_project_code(filepath, enable_logging=True, comment_text="Improved by Code Companion")

                        if success:
                            print("Code improved successfully.")
                        else:
                            print(f"Code improvement failed: {error_message}")

                    except (FileNotFoundError, ValueError) as e:
                        logging.error(f"Error: {e}")
                    except Exception as e:
                        logging.exception(f"An unexpected error occurred during code improvement: {e}")

                elif command == "history":
                    if params[0].lower() == "on":
                        history = True
                    elif params[0].lower() == "off":
                        history = False
                    else:
                        logging.error("Invalid status. Please use 'on' or 'off'.")
                    settings_to_save = {"username": username, "temperature": generation_config["temperature"], "model": current_model, "voice_enabled": voice_enabled, "tone": tone, "output_length": output_length, "window_title": window_title, "pinned": pinned, "opacity": opacity, "agent_name": agent_name, "save_history": save_history, "voice_provider": voice_provider}
                    save_settings(conn, settings_to_save)
                    print(f"\n [{Y}+{X}] Save history {'enabled' if save_history else 'disabled'}.{X}")

                elif command == "rmhistory":
                    database.save_history(conn, [])
                    history = []
                    print(f"Conversation history deleted.")
                else:
                    print(f"{R}Unknown command.{X}")

            else:
                try:
                    agent_message = helper.chat_with_model(user_message, model_name=current_model, chat_session=chat_session, mistral_instance=mistral)
                    print(f" {R}{agent_name}:{X} {agent_message}")
                    if voice_enabled:
                        voice.voice_output(agent_message, voice_provider)
                except Exception as e:
                    logging.exception(f"Error during chat with model: {e}")

    except Exception as e:
        logging.exception(f"An unexpected error occurred in main: {e}")

if __name__ == "__main__":
    main()
