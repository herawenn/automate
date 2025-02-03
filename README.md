# CoPilot by PortLords

![Image](https://i.imgur.com/oIKeBpn.png)

CoPilot is an AI-powered code assistant designed to streamline your coding workflow. It leverages large language models (LLMs) to provide code analysis, improvements, and conversational assistance directly within your development environment. The tool is built using Python and interacts with multiple LLMs.

## Features

* **Code Analysis:** Identifies potential issues in your Python code using `flake8`.
* **Code Improvement:** Automates code style improvements using `autopep8` and AI-powered suggestions.
* **AI-Powered Chat:** Offers a conversational interface for discussing code, debugging, and getting coding assistance.
* **Multi-LLM Support:** Currently supports Google Gemini and Mistral AI, offering flexibility in choosing your preferred model.
* **Voice Integration:** Optionally provides voice output of AI responses via Windows' built-in TTS or ElevenLabs (requires an API key).
* **Persistent Settings & History:** Stores user preferences (temperature, tone, output length, etc.) and chat history in a SQLite database.
* **Memory Management:** Allows you to store and manage persistent memories for context and state.
* **Customizable User Experience:** Allows users to configure their username, agent name, window title, opacity, and more.
* **Improved Error Handling:** Provides more informative error messages and handles exceptions gracefully.
* **Centralized Configuration:** Uses a single `config.json` file for API keys and settings.
* **Code Snippet & Template Library:**  Store and manage reusable code snippets and file templates for quick access and insertion into your projects.

## Getting Started

1. **Prerequisites:**
    * Python 3.8 or higher
    * `pip install -r requirements.txt` (This installs all necessary libraries including `pyperclip`)
    * ElevenLabs API key (and voice id - optional for voice features)
    * Mistral API Key
    * Google Gemini API Key

2. **Configuration:**
    Create a `config.json` file in the root directory with your API keys and settings (see example below).  The `project_directory` setting specifies the folder where your projects will be located.

    ```json
    {
    "db_path": "files/db.db",
    "project_directory": "<desired_project_directory>",
    "window_title": "CoPilot by PortLords",
    "model": "gemini",
    "tone": "professional",
    "output_length": "low",
    "username": "User",
    "agent_name": "Agent",
    "voice_provider": "elevenlabs",
    "temperature": 0.8,
    "voice_enabled": false,
    "pinned": false,
    "opacity": 0.9,
    "save_history": true,
    "gemini_api_key": "<gemini_api_key>",
    "mistral_api_key": "<mistral_api_key>",
    "elevenlabs_api_key": "<elevenlabs_api_key>",
    "valid_voice_id": "<valid_voice_id>",
    "voice_id": "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\TTS_MS_EN-US_ZIRA_11.0"
    }
    ```

3. **Running the Application:**
    Navigate to the root directory of the project in your terminal and run: `python main.py`

4. **Usage:**
    The application starts with a clean console. Type `/commands` to see a list of available commands.


## Commands

The CoPilot tool responds to commands prefixed with a forward slash (`/`).  Here are the available commands:


### General Commands

* `/settings`: Displays current user settings.
* `/commands [<page_number>]`: Displays a list of available commands (paginated).
* `/clear`: Clears the console screen.
* `/specs`: Shows system specifications (CPU, memory, disk).
* `/exit`: Exits the application, saving the chat history (if enabled).

### Customization Commands

* `/username <name>`: Changes the username.
* `/agent <name>`: Changes the agent's name.
* `/title <title>`: Changes the window title.
* `/opacity <value>`: Changes the window opacity (0.0 to 1.0).
* `/temp <value>`: Changes the temperature parameter (affects randomness of AI responses).
* `/tone <casual/formal/professional>`: Changes the tone of AI responses.
* `/output <low/normal/high>`: Changes the length of AI-generated responses.
* `/model <mistral/gemini>`: Sets the AI model to use.
* `/pin`: Toggles the window's "always-on-top" state.


### Interaction Commands
* `/voice <on/off>`: Toggles voice output of responses.
* `/check <filename>`:  Analyzes a file's content using the selected LLM.
* `/improve <filename> <instructions>`: Improves code style and formatting with AI assistance.
* `/create <filename> <description>`: Creates a new file with AI assistance.

### Management Commands
* `/provider <elevenlabs/windows>`: Selects the voice provider.
* `/save_history <on/off>`: Toggles saving conversation history.
* `/rmhistory`: Clears saved conversation history.
* `/memories <add/remove/display/list> <memory>`: Manages stored memories.


### Library Commands
* `/library add`: Adds a new code snippet or template to the library (prompts for name, category, and content).
* `/library remove <ID>`: Removes a library entry by ID.
* `/library list`: Lists all library entries.
* `/library use <ID>`: Uses a library entry (copies code snippets or creates files from templates).


## Project Structure

```md
copilot/
├── main.py               # Main application script
├── helper.py             # Helper functions for code manipulation and AI interaction
├── database.py           # Database interactions (SQLite)
├── voice.py              # Voice input/output handling
└── files/                # Contains the database and log files
    ├── config.json       # Configuration file
    ├── db.db             # SQLite database
    ├── requirements.txt  # Requirements file
    └── logs.txt          # Log file
└── ProjectDir/           # Directory for files
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
