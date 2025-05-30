import speech_recognition as sr
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class VoiceCommandHandler:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        try:
            with self.microphone as source:
                logger.info("Adjusting microphone for ambient noise... please wait.")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                self.recognizer.pause_threshold = 2.0
                logger.info("Microphone adjusted.")
        except Exception as e:
            logger.error(f"Failed to access microphone or adjust for ambient noise: {e}", exc_info=True)
            self.microphone = None

    def listen_and_transcribe(self) -> Optional[str]:
        if not self.microphone:
            logger.error("Microphone not available for voice input.")
            return None

        with self.microphone as source:
            logger.info("Listening for voice command ...")
            print("(Listening for your command...)")
            try:
                audio = self.recognizer.listen(source, timeout=7, phrase_time_limit=45) 
            except sr.WaitTimeoutError:
                logger.info("No speech detected within the initial timeout.")
                print("(No speech detected)")
                return None
            except Exception as e_listen:
                logger.error(f"Error during listening phase: {e_listen}", exc_info=True)
                print("(Error during listening)")
                return None

        logger.info("Processing voice command...")
        print("(Processing your command...)")
        try:
            text = self.recognizer.recognize_google(audio)
            logger.info(f"Voice command transcribed as: '{text}'")
            return text
        except sr.UnknownValueError:
            logger.warning("Google Web Speech API could not understand audio.")
            print("(Could not understand the audio)")
            return None
        except sr.RequestError as e:
            logger.error(f"Could not request results from Google Web Speech API; {e}")
            print(f"(API Error with speech recognition: {e})")
            return None
        except Exception as e_rec:
            logger.error(f"Unexpected error during speech recognition: {e_rec}", exc_info=True)
            print("(Error during speech recognition)")
            return None
