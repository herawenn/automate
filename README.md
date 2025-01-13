# TerminalAI

![Image](https://i.imgur.com/aFha2lm.png)

This is a command-line chatbot application that integrates multiple AI models from different providers (Google Gemini, Cohere, and Mistral). It allows users to interact with these models through a command-line interface, with options to change the system prompt, temperature, and the model being used.

![Image](https://i.imgur.com/cpN5Tm4.png)

## Features

* **Code Analysis:**  Identifies potential issues in your Python code using `flake8`.
* **Code Improvement:** Automates code style improvements using `autopep8`.
* **AI-Powered Chat:**  Offers a conversational interface for discussing code, debugging, and getting coding assistance.
* **Multi-LLM Support:** Currently supports Google Gemini and Mistral AI, offering flexibility in choosing your preferred model.
* **Voice Integration:** Optionally provides voice output of AI responses via Windows' built-in TTS or ElevenLabs (requires an API key).
* **Persistent Settings & History:** Stores user preferences (temperature, tone, output length, etc.) and chat history in a SQLite database.
* **Memory Management:** Allows you to store and manage persistent memories for context and state.
* **Customizable User Experience:**  Allows users to configure their username, agent name, window title, opacity, and more.

![Image](https://i.imgur.com/J5DXVum.png)

## Commands

The Code Companion tool responds to commands prefixed with a forward slash (`/`).  The following commands are available:

* `/settings`: Displays current user settings.
* `/commands`: Displays a list of available commands.
* `/clear`: Clears the console screen.
* `/specs`: Shows system specifications (CPU, memory, disk).
* `/exit`: Exits the application, saving the chat history (if enabled).
* `/username <name>`: Changes the username.
* `/agent <name>`: Changes the agent's name.
* `/title <title>`: Changes the window title.
* `/opacity <value>`: Changes the window opacity (0.0 to 1.0).
* `/temp <value>`: Changes the temperature parameter (affects randomness of responses).
* `/tone <casual/formal/professional>`: Changes the tone of AI responses.
* `/output <low/normal/high>`: Changes the length of AI-generated responses.
* `/pin`: Toggles the window's pinned (always-on-top) state.
* `/voice <on/off>`: Toggles voice output of responses.
* `/provider <elevenlabs/windows>`: Selects the voice provider.
* `/save_history <on/off>`: Toggles saving conversation history to the database.
* `/rmhistory`: Deletes the saved conversation history.
* `/memories <add/remove/display> <memory>`: Manages stored memories.
* `/check <filename>`:  Analyzes a file's content using the selected LLM.
* `/improve <filename>`:  Improves a file's code style and formatting using autopep8.

## Getting Started

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/herawenn/terminalai.git
   cd terminalai
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables:**
    Create a `.env` file in the `files` directory with the following environment variables (replace with your actual keys):

    ```
    DB_PATH=db.db # Path to the database file
    PROJECT_DIRECTORY=<path> # Path to your project directory
    GEMINI_API_KEY=<your_gemini_api_key>
    MISTRAL_API_KEY=<your_mistral_api_key>
    ELEVENLABS_API_KEY=<your_elevenlabs_api_key>
    VALID_VOICE_ID=<your_elevenlabs_voice_id>
    ```

3. **Running the Application:**
    Navigate to the root directory of the project in your terminal and run: `python main.py`

4. **Usage:**
    The application starts with a clean console.  Type `/commands` to see a list of available commands.

## Project Structure

```
terminalAI/
├── main.py          # Main application script
├── helper.py        # Helper functions for code manipulation and AI interaction
├── database.py      # Database interactions (SQLite)
├── voice.py         # Voice input/output handling
└── files/           # Contains the database and log files
    ├── .env         # Environment variables file
    ├── db.db        # SQLite database
    ├── requirements # Requirements file
    └── logs.txt     # Log file
└── ProjectDir/      # Directory for your project files
```

## Additional Notes

The PROJECT_DIRECTORY environment variable specifies the root directory for code analysis and improvement functions. Ensure this is properly set.
For ElevenLabs, you need an account and API key, as well as a valid voice ID.
For Windows-based text-to-speech, it utilizes Windows built-in functionality.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
