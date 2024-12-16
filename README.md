# TerminalAI
![Chatbot Banner](https://i.imgur.com/mSrWMAX.png)

![Imgur](https://i.imgur.com/qEm4JKo.png)

This project is a command-line chatbot application that integrates multiple AI models from different providers (Google Gemini, Cohere, and Mistral). It allows users to interact with these models through a command-line interface, with options to change the system prompt, temperature, and the model being used.

## Features

- **Multiple AI Models**: Integrates Google Gemini, Cohere, and Mistral AI models.
- **Command-Line Interface**: Easy-to-use CLI for interacting with the chatbot.
- **Customizable Settings**: Change the system prompt, temperature, and the model being used.

## Requirements

- Python 3.x
- API keys for Google Gemini, Cohere, and Mistral

## Installation

1. **Clone the Repository**:
    ```sh
    git clone https://github.com/herawenn/terminalai.git
    cd terminalai
    ```

2. **Install Dependencies**:
    ```sh
    pip install google-generativeai cohere mistralai
    ```

3. **Set API Keys**:
    Replace the placeholder API keys in the script with your actual API keys.

    ```python
    GEMINI_API_KEY = 'your_gemini_api_key'
    COHERE_API_KEY = 'your_cohere_api_key'
    MISTRAL_API_KEY = 'your_mistral_api_key'
    ```

## Usage

1. **Run the Script**:
    ```sh
    python terminal.py
    ```

2. **Commands**:
    - `/system <prompt>`: Change the system prompt.
    - `/temp <value>`: Change the temperature.
    - `/model <api>`: Change the API (gemini, cohere, mistral).
    - `/settings`: Show current settings.
    - `/help`: Show this help message.
    - `/clear`: Clear the screen.
    - `/exit`: Quit the conversation.

## Example

```sh
\$ python terminal.py

 Type '/help' for commands, or '/exit' to quit

 From PortLords w Love

 //: Hello, how can I assist you today?
