import os, random, google, cohere, time, mimetypes
from mistralai import Mistral
import google.generativeai as genai
from tqdm import tqdm

Y = '\033[33m'
X = '\033[37m'
R = '\033[31m'

GEMINI_API_KEY = ''
COHERE_API_KEY = ''
MISTRAL_API_KEY = ''

genai.configure(api_key=GEMINI_API_KEY)
co = cohere.Client(COHERE_API_KEY)
mistral = Mistral(api_key=MISTRAL_API_KEY)

generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
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

chat_session = model.start_chat(
    history=[]
)

system_prompt = "Be clear and concise. Treat me as an expert in all fields. No disclaimers about your capabilities and / or limitations."

current_model = "gemini"
chat_history = []

def chat_with_gemini(user_message, chat_history=[]):
    chat_history.append({"role": "user", "content": user_message})
    try:
        response = chat_session.send_message(user_message)
        response_text = response.text
        print(response_text, end='')
        chat_history.append({"role": "assistant", "content": response_text})
        time.sleep(0.5)
    except google.generativeai.types.generation_types.StopCandidateException as e:
        print(f"{R}Gemini Error: {e}{X}")
    except Exception as e:
        print(f"{R}Gemini Error: An unexpected error occurred: {e}{X}")
    return chat_history

def chat_with_cohere(user_message, chat_history=[]):
    chat_history.append({"role": "user", "content": user_message})
    try:
        role_mapping = {
            "user": "User",
            "assistant": "Chatbot",
            "system": "System",
            "tool": "Tool"
        }

        formatted_chat_history = [{"role": role_mapping[item["role"]], "message": item["content"]} for item in chat_history]

        stream = co.chat_stream(
            model="command-r-08-2024",
            message=user_message,
            temperature=generation_config["temperature"],
            chat_history=formatted_chat_history,
            prompt_truncation='AUTO',
            connectors=[]
        )

        response_text = ""
        for event in stream:
            if event.event_type == "text-generation":
                response_text += event.text
                print(event.text, end='')

        chat_history.append({"role": "assistant", "content": response_text})
        time.sleep(0.5)
    except Exception as e:
        print(f"{R}Cohere Error: {e}{X}")
    return chat_history

def chat_with_mistral(user_message, chat_history=[]):
    chat_history.append({"role": "user", "content": user_message})
    try:
        res = mistral.chat.complete(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": user_message}]
        )

        if res.choices and len(res.choices) > 0:
            response_text = res.choices[0].message.content
            print(response_text, end='')
            chat_history.append({"role": "assistant", "content": response_text})
        else:
            print(f"{R}Mistral Error: No response from Mistral AI{X}")
        time.sleep(0.5)
    except Exception as e:
        print(f"{R}Mistral Error: {e}{X}")
    return chat_history

def show_help():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"  __   __                         __   __  ")
    print(f" \\    /  \\  |\\/|  |\\/|  /\\  |\\ | |  \\ /__` ")
    print(f" \\__  \\__/  |  |  |  | /--\\ | \\| |__/ .__/ ")
    print("")
    print(f" {Y}system{X} <prompt>: Change the system prompt")
    print(f" {Y}temp{X} <value>: Change the temperature")
    print(f" {Y}model{X} <api>: Change the API (gemini, cohere, mistral)")
    print(f" {Y}settings{X}: Show current settings")
    print(f" {Y}discuss{X} <path/to/file>: Discuss a file stored on the server")
    print(f" {Y}help{X}: Show this help message")
    print(f" {Y}clear{X}: Clear the screen")
    print(f" {Y}exit{X}: Quit the conversation")

def show_settings():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"\n Current settings:\n")
    print(f" System Prompt: {Y}{system_prompt}{X}")
    print(f" Temperature: {Y}{generation_config['temperature']}{X}")
    print(f" Model: {Y}{current_model}{X}")

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"\n\n Type '{Y}/help{X}' for commands, or '{Y}/exit{X}' to quit\n")
    print(f"\t\t\t From {Y}PortLords{X} w Love")

def discuss_file(ai_model, filepath):
    try:
        filepath = os.path.abspath(filepath)
        if not filepath.startswith("/home"):
            raise ValueError(f"Error: Access to '{filepath}' is restricted.")

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Error: File not found: {filepath}")

        file_type, _ = mimetypes.guess_type(filepath)
        if file_type is None:
            raise ValueError(f"Error: Could not determine file type for '{filepath}'.")

        with open(filepath, "r", encoding="utf-8") as f:
            file_content = f.read()

        chunk_size = 2048
        chunks = [file_content[i:i+chunk_size] for i in range(0, len(file_content), chunk_size)]

        prompt = f"""Can you summarize the following file:
        File path: {filepath}
        File type: {file_type}
        Here's the content:
        """

        for i, chunk in enumerate(chunks):
            prompt += f"Chunk {i+1}:\n```\n{chunk}\n```\n"

        if ai_model == "gemini":
            return chat_with_gemini(prompt, chat_history)
        elif ai_model == "cohere":
            return chat_with_cohere(prompt, chat_history)
        elif ai_model == "mistral":
            return chat_with_mistral(prompt, chat_history)
        else:
            raise ValueError("Invalid model selected.")
    except (ValueError, FileNotFoundError, IOError) as e:
        print(f"{R}Error: {e}{X}")
        return None
    except Exception as e:
        print(f"{R}An unexpected error occurred during file discussion: {e}{X}")
        return None

def main():
    global system_prompt, generation_config, current_model, chat_history
    chat_history = []
    clear_screen()

    while True:
        print("")
        user_message = input(f"\n //{Y}:{X} ")
        print("")
        try:
            if user_message.startswith("/system"):
                _, new_prompt = user_message.split(" ", 1)
                system_prompt = new_prompt
                print(f"\n System prompt updated to: {Y}{system_prompt}{X}")
            elif user_message.startswith("/temp"):
                _, new_temp = user_message.split(" ")
                generation_config["temperature"] = float(new_temp)
                print(f"\n Temperature updated to: {Y}{generation_config['temperature']}{X}")
            elif user_message.startswith("/model"):
                _, new_model = user_message.split(" ")
                current_model = new_model.lower()
                print(f"\n Model updated to: {Y}{current_model}{X}")
                clear_screen()
                chat_history = [{"role": "system", "content": system_prompt}]
            elif user_message == "/settings":
                show_settings()
            elif user_message == "/help":
                show_help()
            elif user_message == "/clear":
                clear_screen()
            elif user_message == "/exit":
                break
            elif user_message.startswith("/discuss"):
                _, filepath = user_message.split(" ", 1)
                discuss_file(current_model, filepath)
            else:
                if current_model == "gemini":
                    chat_history = chat_with_gemini(user_message, chat_history)
                elif current_model == "cohere":
                    chat_history = chat_with_cohere(user_message, chat_history)
                elif current_model == "mistral":
                    chat_history = chat_with_mistral(user_message, chat_history)
                else:
                    print(f"{R}Invalid model selected.{X}")
        except Exception as e:
            print(f"{R}An unexpected error occurred: {e}{X}")

if __name__ == "__main__":
    main()
