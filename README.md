# Automate

![Image](https://i.imgur.com/ft6az2A.png)

This is a Python application designed to streamline your development workflow. It features a robust command-line interface for interacting with the AI, managing project context, and applying code changes. It also supports multimodal input via screen capture and offers voice command capabilities for a more flexible user experience.

## Features

* **AI Model Integration:** Supports multiple AI models including Google's Gemini, Mistral, and Codestral.

* **Project Indexing:** Scans and indexes your project directory to provide relevant context to the AI.

* **Context Management:**
    * Pin specific files or entire directories to the AI's immediate context.
    * Drop files or clear the context as needed.
    * List currently pinned files.

* **Code Interaction:**
    * Propose code changes (new files or modifications to existing ones).
    * Review diffs of proposed changes.
    * Apply or discard AI suggestions.
    * Automatic execution of modified/created Python scripts (if Admin Mode is enabled).

* **Multimodal Input:**
    * `/capture_context`: Captures a screenshot and sends it with a prompt to the AI for analysis (useful for UI elements, error messages, or visual context).

* **Voice Commands:**
    * Activate voice input (default: `Ctrl+Shift+V`) to speak your prompts or commands.

* **Settings Management:**
    * Configure AI model, temperature, and other operational settings.
    * Toggle Admin Mode for enabling/disabling filesystem operations and script execution.

* **Utility Commands:**
    * `/find`: Search for files within the indexed project.
    * `/runtest`: Execute a pre-configured test command for your project.
    * `/reindex`: Manually refresh the project's file index.
    * `/codefolder`: Display the configured project root path.

* **User-Friendly Interface:** Color-coded terminal output for better readability.

* **Persistent Settings:** Saves configuration to a local SQLite database.

* **Logging:** Detailed logging for debugging and tracing operations.

## Components

* **`agent.py`**: Manages the main chatbot logic, command parsing, user interaction, and orchestrates calls to other modules.
* **`indexer.py`**: Handles scanning, indexing, and providing access to files within the specified project code folder.
* **`helper.py`**: Manages API client initialization and communication with the different AI models.
* **`database.py`**: Responsible for storing and retrieving application settings.
* **`main.py`**: The main entry point for the application, handling initial setup and startup.
* **`stream.py`**: Implements screen capture functionality using `mss` and `Pillow`.
* **`voice.py`**: Provides voice command input using `SpeechRecognition`.

## Requirements
The project dependencies are listed in `automate/files/requirements.txt`. Install them using:
```bash
pip install -r requirements.txt
```

## Usage
Run the main application script:
```python
python automate/main.py
```

### Basic Commands
```md
/help: Show available commands.
/list: List currently pinned files and project index summary.
/add <path_in_project>: Pin a file or all files in a directory to the AI's context.
Example: /add main.py or /add src/utils
/drop <filename_or_path_or_all>: Unpin files from the context.
/find <substring>: Search for files in your project by name.
/model [client_name]: View or change the active AI model (e.g., gemini, mistral, codestral).
/settings [key value]: View or modify application settings (e.g., /settings temperature 0.5).
/sudo [on|off]: Toggle Admin Mode (allows file creation/execution by the AI).
/apply: Review and apply AI-proposed code changes.
/discard: Discard the last set of proposed changes.
/capture_context [optional_prompt]: Capture the screen and send it with an optional prompt to the AI.
/runtest [optional_args]: Run the configured test command.
/reindex: Manually rescan the Code Folder.
/clear: Clear the terminal screen.
/quit or /exit: Exit the application.
Ctrl+Shift+V (default): Activate voice input. Speak your command or prompt.
```

## Project Structure
```md
automate/
│
├── main.py                 # Main application entry point, setup, and orchestration
├── agent.py                # Core chatbot logic, command handling, AI interaction
├── helper.py               # API client initialization (Gemini, Mistral, etc.) & interaction
├── indexer.py              # Handles file indexing for project context
├── database.py             # SQLite database interaction for settings
├── stream.py               # Screen capture functionality
├── voice.py                # Voice command input processing
│
├── files/                  # Directory for auxiliary files
│   ├── requirements.txt    # Project dependencies
│   ├── automate.db         # Default SQLite database file (created on run)
│   ├── logs.txt            # Default log file (created on run)
│   └── .env                # Environment variables (user-created)
│
└── Code/                   # Default project folder to be indexed by the assistant (user-created or specified)
    └── ... (your project files and folders to be worked on)
```
## Contributing
Contributions are welcome! Please open an issue or submit a pull request.

## License
This project is licensed under the MIT License - see the LICENSE file for details.
