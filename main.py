import asyncio
import os
import google.generativeai as genai
from aiohttp import web
import logging

# تنظیمات لاگ‌گیری برای نمایش بهتر و دقیق‌تر اطلاعات
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ==============================================================================
# بخش کلید API - لطفاً کلید معتبر خود را اینجا قرار دهید
# ==============================================================================
# کلید API خود را که از Google AI Studio کپی کرده‌اید، در خط زیر بین "" قرار دهید.
API_KEY = "YOUR_API_KEY_HERE" # <--- کلید خود را اینجا جایگزین کنید

# بررسی اولیه برای اطمینان از وارد شدن کلید
if not API_KEY or "YOUR_API_KEY_HERE" in API_KEY:
    raise ValueError("خطا: لطفاً کلید API معتبر خود را در متغیر API_KEY در فایل main.py قرار دهید.")

try:
    genai.configure(api_key=API_KEY)
except Exception as e:
    logging.critical(f"خطا در تنظیمات اولیه Gemini با کلید API ارائه شده: {e}")
    raise

# ==============================================================================

MODEL_NAME = "models/gemini-1.5-pro-latest"
AUDIO_INPUT_SAMPLE_RATE = 16000
AUDIO_OUTPUT_SAMPLE_RATE = 24000

logging.info(f"راه اندازی سرور با مدل: {MODEL_NAME}")

async def forward_to_gemini(client_ws, gemini_session):
    logging.info("آماده برای ارسال داده از کلاینت به Gemini...")
    try:
        while True:
            message = await client_ws.recv()
            if isinstance(message, str):
                await gemini_session.send_request({"text_input": message})
            elif isinstance(message, bytes):
                await gemini_session.send_request({"audio_input": message})
    except asyncio.CancelledError:
        logging.warning("وظیفه ارسال به Gemini لغو شد.")
    except Exception as e:
        logging.error(f"خطا در ارسال به Gemini (ارتباط کلاینت قطع شده): {e}")

async def forward_to_client(client_ws, gemini_session):
    logging.info("آماده برای دریافت داده از Gemini...")
    try:
        async for chunk in gemini_session.response_stream:
            if client_ws.closed:
                break
            if chunk.error:
                error_message = f"خطا از Gemini API: {chunk.error}"
                logging.error(error_message)
                await client_ws.send(f"Error: {error_message}")
                break
            if (text := getattr(chunk, 'text', None)) and text.strip():
                await client_ws.send(f"TEXT: {text}")
            if audio_out := getattr(chunk, 'audio_out', None):
                await client_ws.send(audio_out)
    except asyncio.CancelledError:
        logging.warning("وظیفه ارسال به کلاینت لغو شد.")
    except Exception as e:
        logging.error(f"خطا در دریافت پاسخ از Gemini: {e}")

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logging.info(f"کلاینت جدید متصل شد: {request.remote}")

    gemini_session = None
    try:
        # این نقطه، حساس‌ترین بخش است. خطا معمولا اینجا رخ می‌دهد
        gemini_session = await genai.aideliver.connect(
            model=MODEL_NAME,
            audio_input_format={"sample_rate_hertz": AUDIO_INPUT_SAMPLE_RATE},
            audio_output_format={"sample_rate_hertz": AUDIO_OUTPUT_SAMPLE_RATE},
        )
        logging.info("جلسه (Session) با Gemini با موفقیت ایجاد شد.")
        
        gemini_task = asyncio.create_task(forward_to_gemini(ws, gemini_session))
        client_task = asyncio.create_task(forward_to_client(ws, gemini_session))
        
        await asyncio.gather(gemini_task, client_task)

    except Exception as e:
        # این خطا در ترمینال چاپ خواهد شد
        logging.critical(f"خطای مرگبار در اتصال به Gemini API: {e}", exc_info=True)
    finally:
        logging.info("بستن اتصال...")
        if gemini_session:
            gemini_session.close()
        if not ws.closed:
            await ws.close()
        logging.info(f"ارتباط با {request.remote} بسته شد.")
    return ws

async def http_handler(request):
    return web.FileResponse('./index.html')

async def main():
    app = web.Application()
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/', http_handler)
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"سرور روی http://0.0.0.0:{port} اجرا شد.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.critical(f"خطای اصلی در اجرای برنامه: {e}", exc_info=True)
