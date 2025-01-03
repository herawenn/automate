# TerminalAI

![Imgur](https://i.imgur.com/ldnotS2.png)

This is a command-line chatbot application that integrates multiple AI models from different providers (Google Gemini, Cohere, and Mistral). It allows users to interact with these models through a command-line interface, with options to change the system prompt, temperature, and the model being used.

![Banner](https://i.imgur.com/mSrWMAX.png)

## Features

- **Multiple AI Models**: Integrates Google Gemini, Cohere, and Mistral AI models.
- **Command-Line Interface**: Easy-to-use CLI for interacting with the chatbot.
- **Customizable Settings**: Change the system prompt, temperature, and the model being used.
- **File Discussion:** Analyze and summarize files using the `/discuss` command.


## Update: Add File Discussion Functionality

This update introduces the `/discuss` command, enabling users to provide a file path for AI analysis and summarization.

**Functionality:**

* **File Path Input:** Accepts a file path; verifies file existence and type.
* **File Content Processing:** Reads and processes files in chunks (handling large files).
* **Error Handling:** Handles invalid paths, file not found errors, and AI interaction issues with informative messages (e.g., "File not found" or "API request failed").
* **Security:** Restricts access to files within the `/home` directory.
* **Mimetype Detection:** Uses `mimetypes` for improved file type handling.

**Usage:**

`/discuss <filepath>`  (e.g., `/discuss /home/user/documents/myreport.txt`)


## Requirements

- Python 3.x
- API keys for Google Gemini, Cohere, and Mistral


## Installation

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/herawenn/terminalai.git
   cd terminalai
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set API Keys (Securely!)**:  **Do not hardcode API keys directly into the script.** Use environment variables for security:

   ```bash
   export GEMINI_API_KEY="your_gemini_api_key"
   export COHERE_API_KEY="your_cohere_api_key"
   export MISTRAL_API_KEY="your_mistral_api_key"
   ```
   Then, access them in your Python script using `os.environ.get("GEMINI_API_KEY")`.

## Usage

1. **Run the Script**:
   ```bash
   python terminal.py
   ```

2. **Commands**:
   - `/system <prompt>`: Change the system prompt.
   - `/temp <value>`: Change the temperature.
   - `/model <api>`: Change the API (gemini, cohere, mistral).
   - `/discuss <filepath>`: Analyze the specified file.
   - `/settings`: Show current settings.
   - `/help`: Show this help message.
   - `/clear`: Clear the screen.
   - `/exit`: Quit the conversation.

## Limitations

* Currently supports files up to [Insert File Size Limit, e.g., 5MB].
* May not perfectly handle all file types.
* Performance depends on the speed of the selected AI model and network connection.


## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

[Specify License, e.g., MIT License]
```

Remember to replace `<insert_screenshot_here.png>` with the actual path to your screenshot and fill in the bracketed information.  This improved README provides clearer instructions and addresses potential security concerns.
