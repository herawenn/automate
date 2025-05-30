import os, base64, logging
from typing import Optional, Dict, Any, List, Union
from google import genai
from google.genai import types as google_genai_types
from mistralai import Mistral

logger = logging.getLogger(__name__)

ARCH_AGENT_ENV_VAR = 'ARCHITECT_AGENT_ID'
CODE_AGENT_ENV_VAR = 'CODE_AGENT_ID'

ARCH_AGENT: Optional[str] = os.getenv(ARCH_AGENT_ENV_VAR)
CODE_AGENT: Optional[str] = os.getenv(CODE_AGENT_ENV_VAR)

DEFAULT_GEMINI_MODEL = "gemini-1.5-flash-latest"
DEFAULT_MISTRAL_MODEL = "mistral-large-latest"
DEFAULT_CODESTRAL_MODEL = "codestral-latest"

gemini_client_instance: Optional[genai.Client] = None
mistral_client: Optional[Any] = None
codestral_client: Optional[Any] = None

SUPPORTED_MODELS: Dict[str, Dict[str, Any]] = {}

def init_api_clients(
    gemini_key: Optional[str] = None,
    mistral_key: Optional[str] = None,
    codestral_key: Optional[str] = None
) -> None:
    global gemini_client_instance, mistral_client, codestral_client, SUPPORTED_MODELS

    gemini_client_instance = None
    mistral_client = None
    codestral_client = None
    SUPPORTED_MODELS = {}

    if gemini_key:
        try:
            if not os.getenv('GOOGLE_API_KEY'):
                if gemini_key:
                    logger.info("GOOGLE_API_KEY not set in environment, attempting to use provided gemini_key for this session.")
                    os.environ['GOOGLE_API_KEY'] = gemini_key
                else:
                    logger.warning("GEMINI_API_KEY provided to init_api_clients, but it's empty. Cannot set GOOGLE_API_KEY.")

            gemini_client_instance = genai.Client()

            logger.info(f"Gemini client (genai.Client) initialized. Default model for requests: {DEFAULT_GEMINI_MODEL}.")
            SUPPORTED_MODELS["gemini"] = {
                "client": gemini_client_instance,
                "type": "gemini_client_models",
                "name": DEFAULT_GEMINI_MODEL
            }
        except AttributeError as ae:
            logger.error(f"Failed Gemini client init (AttributeError): {ae}. "
                         f"Issue with 'genai.Client()' or related methods. Ensure 'from google import genai' is correct and library is installed/updated.", exc_info=True)
            gemini_client_instance = None
            if os.getenv('GOOGLE_API_KEY') == gemini_key:
                del os.environ['GOOGLE_API_KEY']
        except Exception as e:
            logger.error(f"Failed Gemini client init: {e}", exc_info=True)
            gemini_client_instance = None
            if os.getenv('GOOGLE_API_KEY') == gemini_key:
                del os.environ['GOOGLE_API_KEY']
    else:
        logger.warning("GEMINI_API_KEY not provided to init_api_clients. Gemini client disabled.")

    if mistral_key:
        try:
            mistral_client = Mistral(api_key=mistral_key)
            logger.info("Mistral client initialized.")
            SUPPORTED_MODELS["mistral"] = {"client": mistral_client, "type": "mistral_client", "name": DEFAULT_MISTRAL_MODEL}
            if not CODE_AGENT: logger.warning(f"CODE_AGENT (target ID for Mistral code tasks) is not configured (env var '{CODE_AGENT_ENV_VAR}' missing or empty, and no default). Mistral 'code' hint may not use specialized agent.")
            if not ARCH_AGENT: logger.warning(f"ARCH_AGENT (target ID for Mistral conversation tasks) is not configured (env var '{ARCH_AGENT_ENV_VAR}' missing or empty, and no default). Mistral 'conversation' hint may not use specialized agent.")
        except AttributeError as ae:
            logger.error(f"Failed Mistral client init (AttributeError): {ae}. "
                         f"Ensure 'from mistralai import Mistral' (or correct client class) is used and library is installed/updated.", exc_info=True)
            mistral_client = None
        except Exception as e:
            logger.error(f"Failed Mistral client init: {e}", exc_info=True)
            mistral_client = None
    else:
        logger.warning("MISTRAL_API_KEY not provided. Mistral client disabled.")

    if codestral_key:
        if codestral_key == mistral_key and mistral_client:
             logger.info("Codestral key is the same as Mistral key, and Mistral client is active. Using existing Mistral client for Codestral.")
             codestral_client = mistral_client
        else:
            try:
                codestral_client = Mistral(api_key=codestral_key)
                logger.info("Codestral client initialized (potentially new instance).")
            except Exception as e:
                logger.error(f"Failed Codestral client init: {e}", exc_info=True)
                codestral_client = None

        if codestral_client:
            SUPPORTED_MODELS["codestral"] = {"client": codestral_client, "type": "mistral_client", "name": DEFAULT_CODESTRAL_MODEL}
    else:
        logger.warning("CODESTRAL_API_KEY not provided. Codestral client disabled.")

    if not SUPPORTED_MODELS:
        logger.warning("init_api_clients: No AI clients could be initialized successfully.")
    else:
        logger.info(f"init_api_clients: Supported model clients after initialization: {list(SUPPORTED_MODELS.keys())}")


GoogleGenAIContentType = Union[str, Dict[str, str], google_genai_types.Part]

def chat_with_model(
    user_content_parts: List[GoogleGenAIContentType],
    model_name: str = "gemini",
    mode_hint: str = 'code'
) -> str:
    try:
        model_config = SUPPORTED_MODELS.get(model_name.lower())
        if not model_config or not model_config.get("client"):
            available_clients = list(SUPPORTED_MODELS.keys())
            err_msg = f"Error: Client for AI system '{model_name}' is not available or not initialized. Available clients: {available_clients}"
            logger.error(err_msg)
            return err_msg

        client_object = model_config["client"]
        api_type = model_config["type"]
        target_model_identifier = model_config["name"]

        effective_gemini_model_str = target_model_identifier
        if api_type == 'gemini_client_models':
            if not target_model_identifier.startswith("models/"):
                effective_gemini_model_str = f"models/{target_model_identifier}"

        actual_model_target_for_mistral_type = target_model_identifier
        if api_type == 'mistral_client':
            if model_name == 'mistral':
                if mode_hint == 'code' and CODE_AGENT:
                    actual_model_target_for_mistral_type = CODE_AGENT
                    logger.info(f"Routing to Mistral CODE_AGENT: {actual_model_target_for_mistral_type} for '{model_name}' (code hint).")
                elif mode_hint == 'conversation' and ARCH_AGENT:
                    actual_model_target_for_mistral_type = ARCH_AGENT
                    logger.info(f"Routing to Mistral ARCH_AGENT: {actual_model_target_for_mistral_type} for '{model_name}' (conversation hint).")

        processed_api_content: Any
        is_multimodal_gemini_request = False

        if api_type == 'gemini_client_models':
            gemini_contents_list = []
            for part_item in user_content_parts:
                if isinstance(part_item, str):
                    gemini_contents_list.append(google_genai_types.Part(text=part_item))
                elif isinstance(part_item, dict) and "mime_type" in part_item and "data" in part_item:
                    try:
                        img_bytes = base64.b64decode(part_item["data"])
                        image_blob = google_genai_types.Blob(mime_type=part_item["mime_type"], data=img_bytes)
                        image_part = google_genai_types.Part(inline_data=image_blob)
                        gemini_contents_list.append(image_part)
                        is_multimodal_gemini_request = True
                    except Exception as e_img:
                        logger.error(f"Error processing image part for Gemini (Client): {e_img}", exc_info=True)
                        return f"Error: Could not process image data for Gemini. {e_img}"
                elif isinstance(part_item, google_genai_types.Part):
                    gemini_contents_list.append(part_item)
                    if part_item.inline_data and part_item.inline_data.mime_type.startswith("image/"):
                        is_multimodal_gemini_request = True
                else:
                    logger.warning(f"Unsupported content part type for Gemini (Client): {type(part_item)}")
                    return f"Error: Unsupported content part type '{type(part_item)}' for Gemini."
            processed_api_content = gemini_contents_list

        elif api_type == 'mistral_client':
            combined_text = ""
            has_non_text_parts = False
            for part_item in user_content_parts:
                if isinstance(part_item, str):
                    combined_text += part_item + "\n"
                elif isinstance(part_item, dict) and "mime_type" in part_item:
                    logger.warning(f"Image data provided for Mistral/Codestral model '{actual_model_target_for_mistral_type}'. Mistral client typically handles text-only. Image will be ignored.")
                    has_non_text_parts = True

            if not combined_text.strip():
                if has_non_text_parts:
                    return f"Error: No textual content provided for Mistral/Codestral model '{actual_model_target_for_mistral_type}'. Image data is ignored by this client."
                return f"Error: No text content provided for Mistral/Codestral model '{actual_model_target_for_mistral_type}'."

            processed_api_content = [{"role": "user", "content": combined_text.strip()}]
        else:
            logger.error(f"Internal Error: No content processing logic defined for api_type '{api_type}'.")
            return f"Error: Internal configuration error - unknown api_type '{api_type}'."

        target_for_logging = effective_gemini_model_str if api_type == 'gemini_client_models' else actual_model_target_for_mistral_type
        logger.debug(f"Sending request to AI: model_name_key='{model_name}', api_type='{api_type}', actual_target='{target_for_logging}', mode_hint='{mode_hint}'.")

        if api_type == "gemini_client_models":
            if not isinstance(client_object, genai.Client):
                logger.error(f"Gemini client (client_object) is not a genai.Client instance. Type: {type(client_object)}")
                return "Error: Misconfigured Gemini client instance."

            gemini_request_config: Optional[google_genai_types.GenerateContentConfig] = None

#             if mode_hint == 'code':
#                 gemini_request_config = google_genai_types.GenerateContentConfig(
#                     stop_sequences=["```"]
#                 )
#                 logger.debug("Applying stop_sequences for Gemini (Client) via GenerateContentConfig object passed to 'config' parameter.")

            response = client_object.models.generate_content(
                model=effective_gemini_model_str,
                contents=processed_api_content,
                config=gemini_request_config
            )

            if not response.candidates:
                 reason = "Unknown"; block_reason_message = ""
                 if hasattr(response, 'prompt_feedback'):
                     if response.prompt_feedback and hasattr(response.prompt_feedback, 'block_reason'):
                         reason = response.prompt_feedback.block_reason.name
                         if hasattr(response.prompt_feedback, 'block_reason_message') and response.prompt_feedback.block_reason_message:
                             block_reason_message = f" Message: {response.prompt_feedback.block_reason_message}"
                 logger.warning(f"Gemini response was blocked or empty. Reason: {reason}{block_reason_message}. Full feedback: {getattr(response, 'prompt_feedback', 'N/A')}")
                 return f"Error: AI response blocked or empty (Reason: {reason}).{block_reason_message}"

            agent_message = ""
            try:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text is not None:
                        agent_message += part.text
            except (IndexError, AttributeError) as e_resp_parse:
                logger.warning(f"Could not parse text from Gemini response candidate: {e_resp_parse}. Candidates: {response.candidates}", exc_info=True)
                finish_reason_str = "N/A"
                try:
                    if response.candidates and hasattr(response.candidates[0], 'finish_reason'):
                        finish_reason_str = response.candidates[0].finish_reason.name
                except Exception: pass
                return f"Error: Could not extract text from AI response. Finish Reason: {finish_reason_str}."

            if not agent_message.strip() and not is_multimodal_gemini_request:
                logger.warning(f"Gemini response (Client) resulted in no text. Candidates: {response.candidates}")
                finish_reason_str = "N/A"
                try:
                    if response.candidates and hasattr(response.candidates[0], 'finish_reason') and response.candidates[0].finish_reason:
                        finish_reason_str = response.candidates[0].finish_reason.name
                except Exception: pass

                if finish_reason_str not in ["STOP", "MAX_TOKENS"]:
                    return f"Error: Gemini AI returned no text. Finish Reason: {finish_reason_str}."
            return agent_message

        elif api_type == "mistral_client":
             if not isinstance(client_object, Mistral):
                 logger.error(f"Mistral/Codestral client object is of wrong type: {type(client_object)}. Expected Mistral.")
                 return "Error: Internal configuration error - Mistral client type mismatch."

             chat_response = client_object.chat(
                 model=actual_model_target_for_mistral_type,
                 messages=processed_api_content
             )
             if chat_response.choices:
                 agent_message: str = chat_response.choices[0].message.content
             else:
                 logger.warning(f"Mistral/Codestral response had no choices. Response: {chat_response}")
                 return "Error: AI response from Mistral/Codestral was empty or malformed (no choices)."
             return agent_message
        else:
            logger.error(f"Internal Error: Invalid api_type '{api_type}' encountered during API call phase.")
            return f"Error: Internal routing error (unhandled api_type: {api_type})."

    except AttributeError as e_attr:
        logger.error(f"AttributeError during AI API call (model='{model_name}', hint='{mode_hint}'): {e_attr}", exc_info=True)
        return f"Error: AI SDK attribute error for model '{model_name}' ('{e_attr}'). This might indicate an issue with the AI library version or incorrect client usage."
    except Exception as e_unexpected:
        logger.exception(f"Unexpected error during AI API call (model='{model_name}', hint='{mode_hint}'): {e_unexpected}")
        err_str_lower = str(e_unexpected).lower()
        if "api key" in err_str_lower or "authentication" in err_str_lower:
            return f"Error: API Key or Authentication issue for AI model '{model_name}'."
        if "user location is not supported" in str(e_unexpected).lower():
            logger.error(f"Gemini API specific error: User location not supported. Details: {e_unexpected}")
            return "Error: Gemini API - User location is not supported for use."
        return f"Error: An unexpected error occurred with the AI call for model '{model_name}' (Type: {type(e_unexpected).__name__}). Please check the application logs."
