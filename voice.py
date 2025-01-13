import os
import logging
import pyttsx3
from elevenlabs import Voice, VoiceSettings, play
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'files', '.env'))

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s',
                    handlers=[logging.FileHandler('files/logs.txt'),
                              logging.StreamHandler()])


ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
VALID_VOICE_ID = os.getenv('VALID_VOICE_ID')
client = ElevenLabs(api_key=ELEVENLABS_API_KEY) if ELEVENLABS_API_KEY else None

def voice_output(text, voice_provider="elevenlabs"):
    try:
        if voice_provider == "elevenlabs" and client:
            voice_settings = VoiceSettings(
                stability=0.90,
                similarity_boost=0.85,
                style=0.20,
                use_speaker_boost=True,
                speed=6  # Social grace
            )
            logging.info(f"Generating ElevenLabs voice output for: {text}")
            try:
                audio = client.generate(
                    text=text,
                    voice=Voice(
                        voice_id=VALID_VOICE_ID,
                        settings=voice_settings
                    )
                )
                play(audio)
                logging.info("ElevenLabs voice output played successfully.")
                return True, ""
            except Exception as e:
                logging.exception(f"ElevenLabs API Error: {e}")
                return False, f"ElevenLabs API Error: {e}"

        elif voice_provider in ["free", "windows"]:
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
            logging.info(f"{voice_provider.capitalize()} Voice Output: {text}")
            return True, ""
        else:
            logging.warning(f"Unsupported voice provider: {voice_provider}")
            return False, "Unsupported voice provider"

    except Exception as e:
        logging.exception(f"An unexpected error occurred during voice output: {e}")
        return False, f"An unexpected error occurred during voice output: {e}"
