import io, base64, asyncio, logging, mss
from typing import Optional, Dict
import mss.tools
import PIL.Image

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    _handler = logging.StreamHandler()
    _formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

class ScreenGrabber:
    def __init__(self):
        try:
            mss.mss() 
        except Exception as e:
            logger.error(f"Failed to pre-initialize mss in ScreenGrabber: {e}", exc_info=True)

    def _capture_screen_to_png_bytes(self) -> Optional[bytes]:
        try:
            with mss.mss() as sct:
                if len(sct.monitors) >= 2:
                    monitor_to_capture = sct.monitors[1]
                else:
                    logger.warning("Primary monitor (index 1) not found. Capturing entire virtual screen (index 0).")
                    monitor_to_capture = sct.monitors[0]

                sct_img = sct.grab(monitor_to_capture)
                img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
                logger.debug(f"Screen captured successfully ({sct_img.width}x{sct_img.height}).")
                return img_bytes
        except mss.exception.ScreenShotError as e:
            logger.error(f"MSS ScreenShotError during screen capture: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Generic error during MSS screen capture: {e}", exc_info=True)
            return None

    def get_screen_capture_base64(self, output_format: str = "PNG") -> Optional[Dict[str, str]]:
        try:
            png_image_bytes = self._capture_screen_to_png_bytes()
            if not png_image_bytes:
                return None

            final_image_bytes = png_image_bytes
            mime_type = "image/png"
            requested_format = output_format.upper()

            if requested_format == "JPEG":
                try:
                    pil_image = PIL.Image.open(io.BytesIO(png_image_bytes))
                    if pil_image.mode in ('RGBA', 'LA', 'P'):
                        pil_image = pil_image.convert('RGB')
                    
                    jpeg_buffer = io.BytesIO()
                    pil_image.save(jpeg_buffer, format="JPEG", quality=85)
                    final_image_bytes = jpeg_buffer.getvalue()
                    mime_type = "image/jpeg"
                    logger.debug("Converted screenshot to JPEG format.")
                except Exception as e:
                    logger.error(f"Error converting image to JPEG: {e}. Falling back to PNG.", exc_info=True)
            elif requested_format != "PNG":
                logger.warning(f"Unsupported image format: {output_format}. Defaulting to PNG.")

            encoded_string = base64.b64encode(final_image_bytes).decode('utf-8')
            
            return {
                "mime_type": mime_type,
                "data": encoded_string
            }
        except Exception as e:
            logger.error(f"Error in get_screen_capture_base64: {e}", exc_info=True)
            return None

    async def capture_screen_base64_async(self, output_format: str = "PNG") -> Optional[Dict[str, str]]:
        try:
            if not isinstance(output_format, str):
                logger.warning(f"output_format was not a string ({type(output_format)}), defaulting to PNG.")
                output_format = "PNG"

            result = await asyncio.to_thread(self.get_screen_capture_base64, output_format)
            return result
        except Exception as e:
            logger.error(f"Error in async screen capture execution: {e}", exc_info=True)
            return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger_main = logging.getLogger(__name__)

    async def main_test():
        grabber = ScreenGrabber()
        
        logger_main.info("Testing synchronous capture (PNG)...")
        capture_data_png_sync = grabber.get_screen_capture_base64(output_format="PNG")
        if capture_data_png_sync:
            logger_main.info(f"PNG Sync Capture successful: mime_type={capture_data_png_sync['mime_type']}, data length={len(capture_data_png_sync['data'])}")
        else:
            logger_main.error("PNG Sync Capture failed.")

        logger_main.info("Testing synchronous capture (JPEG)...")
        capture_data_jpeg_sync = grabber.get_screen_capture_base64(output_format="JPEG")
        if capture_data_jpeg_sync:
            logger_main.info(f"JPEG Sync Capture successful: mime_type={capture_data_jpeg_sync['mime_type']}, data length={len(capture_data_jpeg_sync['data'])}")
        else:
            logger_main.error("JPEG Sync Capture failed.")
        
        logger_main.info("Testing synchronous capture (INVALID FORMAT -> should default to PNG)...")
        capture_data_invalid_sync = grabber.get_screen_capture_base64(output_format="GIF")
        if capture_data_invalid_sync and capture_data_invalid_sync['mime_type'] == "image/png":
            logger_main.info(f"Invalid Format Sync Capture successful (defaulted to PNG): mime_type={capture_data_invalid_sync['mime_type']}, data length={len(capture_data_invalid_sync['data'])}")
        elif capture_data_invalid_sync:
            logger_main.error(f"Invalid Format Sync Capture returned unexpected mime_type: {capture_data_invalid_sync['mime_type']}")
        else:
            logger_main.error("Invalid Format Sync Capture failed.")

        logger_main.info("Testing asynchronous capture (PNG)...")
        capture_data_png_async = await grabber.capture_screen_base64_async(output_format="PNG")
        if capture_data_png_async:
            logger_main.info(f"Async PNG Capture successful: mime_type={capture_data_png_async['mime_type']}, data length={len(capture_data_png_async['data'])}")
        else:
            logger_main.error("Async PNG Capture failed.")
        
        logger_main.info("Testing asynchronous capture (JPEG)...")
        capture_data_jpeg_async = await grabber.capture_screen_base64_async(output_format="JPEG")
        if capture_data_jpeg_async:
            logger_main.info(f"Async JPEG Capture successful: mime_type={capture_data_jpeg_async['mime_type']}, data length={len(capture_data_jpeg_async['data'])}")
        else:
            logger_main.error("Async JPEG Capture failed.")

    asyncio.run(main_test())
