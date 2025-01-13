import os
import sys
import shutil
import logging
from tempfile import NamedTemporaryFile
from dotenv import load_dotenv
import autopep8
import subprocess
import re
import google.generativeai as genai
from mistralai import Mistral

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'files', '.env'))

#Set Project Directory from .env file
PROJECT_DIRECTORY = os.getenv("PROJECT_DIRECTORY")

# Configure logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s',
                    handlers=[logging.FileHandler('files/logs.txt'), logging.StreamHandler()])

def _create_clone(filepath):
    logging.debug(f"Creating clone of: {filepath}")
    try:
        with open(filepath, 'r') as src, NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp:
            shutil.copyfileobj(src, temp)
            clone_path = temp.name
            return True, clone_path
    except (IOError, OSError) as e:
        return False, f"Error creating clone of '{filepath}': {e}"

def _run_flake8(filepath):
    logging.debug(f"Running flake8 on file: {filepath}")
    try:
        process = subprocess.Popen([sys.executable, "-m", "flake8", os.path.basename(filepath)], cwd=PROJECT_DIRECTORY, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        if stderr:
            return False, stderr
        else:
            return True, stdout

    except FileNotFoundError:
        return False, "Flake8 not found. Please ensure it is installed."
    except Exception as e:
        return False, f"An unexpected error occurred during flake8 execution: {e}"

def chat_with_model(user_message, model_name, chat_session=None, mistral_instance=None):
    try:
        if model_name == "gemini":
            if chat_session is None:
                raise ValueError("Gemini chat session not provided.")
            response = chat_session.send_message(user_message)
            agent_message = response.text
            return agent_message
        elif model_name == "mistral":
            if mistral_instance is None:
                raise ValueError("Mistral instance not provided.")
            response = mistral_instance.chat(user_message)
            agent_message = response
            return agent_message
        else:
            raise ValueError(f"Unsupported model: {model_name}")
    except ValueError as e:
        logging.error(f"Error in chat_with_model: {e}")
        return f"Error: {e}"
    except Exception as e:
        logging.exception(f"An unexpected error occurred in chat_with_model: {e}")
        return f"An unexpected error occurred: {e}"

def improve_project_code(filepath, file_extensions=('.py'), enable_logging=True, comment_text="code companion was here", run_flake8=True):
    if not os.path.exists(filepath):
        if enable_logging:
            logging.error(f"File '{filepath}' not found.")
        return False, "File not found."

    if not os.path.isfile(filepath):
        if enable_logging:
            logging.error(f"'{filepath}' is not a file.")
        return False, "'{filepath}' is not a file."

    if enable_logging:
        logging.info(f"Processing file: {filepath}")

    clone_success, clone_path = _create_clone(filepath)
    if not clone_success:
        return False, clone_path

    original_directory = os.getcwd()
    try:
        os.chdir(PROJECT_DIRECTORY)

        if run_flake8:
            flake8_success, flake8_output = _run_flake8(os.path.basename(filepath))
            if not flake8_success:
                return False, flake8_output
            if enable_logging:
                logging.info(f"Flake8 output for {filepath}:\n{flake8_output}")

        try:
            os.remove(clone_path)
        except OSError as e:
            logging.error(f"Error removing clone file: {e}")
            return False, f"Error removing clone file: {e}"

    finally:
        os.chdir(original_directory)

    if enable_logging:
        logging.info(f"Successfully processed file: {filepath}")

    return True, ""
