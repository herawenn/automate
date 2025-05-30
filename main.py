import os, sys, logging
import agent,database,helper
from typing import Optional
from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv

# --- Constants ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ENV_PATH = os.path.join(PROJECT_ROOT, 'files/.env')
DEFAULT_LOG_FILENAME = 'files/logs.txt'
DEFAULT_DB_FILENAME = 'files/automate.db'
DEFAULT_CODE_FOLDER_NAME = 'Code'

try:
    env_path_to_load = os.getenv('AUTOMATE_ENV_PATH', DEFAULT_ENV_PATH)
    if os.path.exists(env_path_to_load):
        load_dotenv(dotenv_path=env_path_to_load)
    else:
        if env_path_to_load == DEFAULT_ENV_PATH:
            print(f"{Fore.YELLOW}Warning: Default .env file not found at {DEFAULT_ENV_PATH}. "
                  f"Relying on system environment variables if set.{Style.RESET_ALL}")
except Exception as e_dotenv:
    print(f"{Fore.RED}Error loading .env file: {e_dotenv}{Style.RESET_ALL}")

# --- Paths ---
LOG_FILE_PATH = os.path.join(PROJECT_ROOT, os.getenv('LOG_FILE_PATH', DEFAULT_LOG_FILENAME))
DATABASE_PATH = os.path.join(PROJECT_ROOT, os.getenv('DATABASE_PATH', DEFAULT_DB_FILENAME))
CODE_FOLDER_PATH = os.path.join(PROJECT_ROOT, os.getenv('CODE_FOLDER_PATH', DEFAULT_CODE_FOLDER_NAME))

# --- API Keys ---
GEMINI_API_KEY: Optional[str] = os.getenv('GEMINI_API_KEY')
MISTRAL_API_KEY: Optional[str] = os.getenv('MISTRAL_API_KEY')
CODESTRAL_API_KEY: Optional[str] = os.getenv('CODESTRAL_API_KEY')
DEFAULT_ADMIN_MODE_ENV: Optional[str] = os.getenv('DEFAULT_ADMIN_MODE_ENABLED')
CODE_AGENT_ID: Optional[str] = os.getenv('CODE_AGENT_ID')
ARCHITECT_AGENT_ID: Optional[str] = os.getenv('ARCHITECT_AGENT_ID')

# --- Initialization ---
try:
    colorama_init(autoreset=True)
except Exception as e_colorama:
    print(f"Warning: Failed to initialize colorama: {e_colorama}. Colored output might not work.")

# --- Logging ---
logger: Optional[logging.Logger] = None
try:
    log_dir = os.path.dirname(LOG_FILE_PATH)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE_PATH, encoding='utf-8', mode='a'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger("automate_main")
    logger.info("Logging configured successfully.")
    logger.info(f"Directory set to: {CODE_FOLDER_PATH}")

except OSError as e_log_os:
    print(f"{Fore.RED}{Style.BRIGHT}Fatal Error: Could not create log directory or file '{LOG_FILE_PATH}': {e_log_os}{Style.RESET_ALL}")
    sys.exit(1)
except Exception as e_log_generic:
     print(f"{Fore.RED}{Style.BRIGHT}Fatal Error: Could not configure logging: {e_log_generic}{Style.RESET_ALL}")
     sys.exit(1)


def main_application_logic():

    if not logger:
        print(f"{Fore.RED}{Style.BRIGHT}Fatal Error: Logger not initialized.{Style.RESET_ALL}")
        sys.exit(1)

    logger.info("AI Coding Assistant (Project Indexed Edition) starting...")

    try:
        helper.init_api_clients(
            gemini_key=GEMINI_API_KEY,
            mistral_key=MISTRAL_API_KEY,
            codestral_key=CODESTRAL_API_KEY
        )
        if not helper.SUPPORTED_MODELS:
             logger.critical("No AI models could be initialized. Check API keys and previous logs.")
             print(f"{Fore.RED}{Style.BRIGHT}Fatal Error: Failed to initialize any AI models. "
                   f"Please check your API keys and application logs.{Style.RESET_ALL}")
             sys.exit(1)
        logger.info(f"AI Clients Initialized. Supported models: {list(helper.SUPPORTED_MODELS.keys())}")
    except Exception as e_api_init:
        logger.critical(f"Fatal error during API client initialization: {e_api_init}", exc_info=True)
        print(f"{Fore.RED}{Style.BRIGHT}Fatal Error: Could not initialize AI clients: {e_api_init}{Style.RESET_ALL}")
        sys.exit(1)

    db_connection = None
    try:
        db_connection = database.connect(db_path=DATABASE_PATH)
        if not db_connection:
             logger.critical(f"Database connection function returned None for path: {DATABASE_PATH}.")
             print(f"{Fore.RED}{Style.BRIGHT}Error: Could not establish database connection (connect returned None).{Style.RESET_ALL}")
             sys.exit(1)
        logger.info(f"Database connection established: {DATABASE_PATH}")
    except database.ConnectionError as db_err:
         logger.critical(f"Failed to connect to the database at {DATABASE_PATH}: {db_err}", exc_info=True)
         print(f"{Fore.RED}{Style.BRIGHT}Fatal Error: Could not connect to the database. "
               f"Check path/permissions: {DATABASE_PATH}{Style.RESET_ALL}")
         print(f"{Fore.RED}{Style.DIM}Details: {db_err}{Style.RESET_ALL}")
         sys.exit(1)
    except Exception as e_db_unexpected:
        logger.critical(f"Unexpected error connecting to database {DATABASE_PATH}: {e_db_unexpected}", exc_info=True)
        print(f"{Fore.RED}{Style.BRIGHT}Fatal Error: Unexpected database connection issue: {e_db_unexpected}{Style.RESET_ALL}")
        sys.exit(1)

    chatbot_instance = None
    try:
        chatbot_instance = agent.ChatBot(
            db_conn=db_connection,
            code_folder_path=CODE_FOLDER_PATH, 
            default_admin_mode=DEFAULT_ADMIN_MODE_ENV
        )
        logger.info("ChatBot initialized. Starting interaction loop...")
        chatbot_instance.start()

    except RuntimeError as rt_err:
        logger.critical(f"ChatBot initialization failed with RuntimeError: {rt_err}", exc_info=True)
        print(f"{Fore.RED}{Style.BRIGHT}Fatal Error during ChatBot setup: {rt_err}. Check logs at {LOG_FILE_PATH}{Style.RESET_ALL}")
        if db_connection: db_connection.close()
        sys.exit(1)
    except Exception as e_chatbot:
        logger.exception("An unexpected error occurred during ChatBot initialization or execution.")
        print(f"{Fore.RED}{Style.BRIGHT}Fatal Error: An unexpected issue with the ChatBot occurred: {e_chatbot}. "
              f"Check logs at {LOG_FILE_PATH} for details.{Style.RESET_ALL}")
        if db_connection: db_connection.close()
        sys.exit(1)
    
    logger.info("AI Coding Assistant finished normally.")

def run_initial_checks_and_setup():
    if not GEMINI_API_KEY and not MISTRAL_API_KEY and not CODESTRAL_API_KEY:
        print(f"{Fore.RED}{Style.BRIGHT}Fatal Error: At least one API key (GEMINI_API_KEY, MISTRAL_API_KEY, or CODESTRAL_API_KEY) "
              f"must be configured in your .env file or system environment.{Style.RESET_ALL}")
        sys.exit(1)
    
    try:
        if not os.path.exists(CODE_FOLDER_PATH):
            print(f"{Fore.YELLOW}Note: Code Folder at '{CODE_FOLDER_PATH}' does not exist. It will be created.{Style.RESET_ALL}")
            os.makedirs(CODE_FOLDER_PATH, exist_ok=True)
        elif not os.path.isdir(CODE_FOLDER_PATH):
            print(f"{Fore.RED}{Style.BRIGHT}Fatal Error: The configured Code Folder path '{CODE_FOLDER_PATH}' exists but is not a directory.{Style.RESET_ALL}")
            sys.exit(1)
    except OSError as e_codefolder:
        print(f"{Fore.RED}{Style.BRIGHT}Fatal Error: Could not create or access Code Folder at '{CODE_FOLDER_PATH}': {e_codefolder}{Style.RESET_ALL}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        run_initial_checks_and_setup()
        main_application_logic()
    except SystemExit:
        if logger: logger.info("Application exiting via SystemExit.")
        else: print("Application exiting.")
    except Exception as e_main_unhandled:
        final_error_message = f"Unhandled critical error in main execution: {e_main_unhandled}"
        print(f"{Fore.RED}{Style.BRIGHT}{final_error_message}{Style.RESET_ALL}")
        if logger:
            logger.critical(final_error_message, exc_info=True)
        sys.exit(1)
