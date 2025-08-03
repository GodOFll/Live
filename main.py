import asyncio
import os
import google.generativeai as genai
from aiohttp import web
import logging

# تنظیمات لاگ‌گیری برای نمایش بهتر اطلاعات
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ==============================================================================
# بخش کلید API - لطفاً دقت کنید
# ==============================================================================
# هشدار بسیار مهم امنیتی:
# قرار دادن کلید API مستقیماً در کد، یک ریسک امنیتی است.
# اگر این کد را در یک مخزن عمومی (مانند گیت‌هاب) قرار می‌دهید، هر کسی می‌تواند
# از کلید شما استفاده کند. با این حال، طبق درخواست شما، محل قرار دادن کلید
# در اینجا مشخص شده است.

# لطفاً کلید API خود را در خط زیر بین علامت‌های نقل قول "" قرار دهید.
API_KEY = "AIzaSyBoiWCq4k9w5-Uq5XtspwLylMWrrDvEE0Q"

# بررسی اینکه آیا کاربر کلید را وارد کرده است یا خیر
if not API_KEY or "YOUR_API_KEY_HERE" in API_KEY:
    raise ValueError("خطا: لطفاً کلید API معتبر خود را در متغیر API_KEY در فایل main.py قرار دهید.")

genai.configure(api_key=API_KEY)
# ==============================================================================

# استفاده از قوی‌ترین مدل موجود برای ارتباط زنده و دقیق
MODEL_NAME = "models/gemini-1.5-pro-latest"
AUDIO_INPUT_SAMPLE_RATE = 16000
AUDIO_OUTPUT_SAMPLE_RATE = 24000

logging.info(f"راه اندازی سرور پایتون برای Gemini Live API با مدل: {MODEL_NAME}")

async def forward_to_gemini(client_ws, gemini_session):
    """داده‌ها را از کلاینت دریافت کرده و به Gemini ارسال می‌کند."""
    logging.info("آماده برای ارسال داده از کلاینت به Gemini...")
    try:
        while True:
            message = await client_ws.recv()
            if isinstance(message, str):
                # کلید صحیح بر اساس مستندات برای ارسال متن: 'text_input'
                logging.info(f"ارسال متن به Gemini: {message[:60]}...")
                await gemini_session.send_request({"text_input": message})
            elif isinstance(message, bytes):
                # کلید صحیح بر اساس مستندات برای ارسال صدا: 'audio_input'
                await gemini_session.send_request({"audio_input": message})
    except asyncio.CancelledError:
        logging.warning("وظیفه ارسال به Gemini لغو شد.")
    except Exception as e:
        logging.error(f"خطا در ارسال به Gemini (ارتباط کلاینت قطع شده): {e}", exc_info=True)

async def forward_to_client(client_ws, gemini_session):
    """پاسخ‌ها را از Gemini دریافت کرده و به کلاینت ارسال می‌کند."""
    logging.info("آماده برای دریافت داده از Gemini و ارسال به کلاینت...")
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
                logging.info(f"دریافت متن از Gemini: {text}")
                await client_ws.send(f"TEXT: {text}")
                
            if audio_out := getattr(chunk, 'audio_out', None):
                await client_ws.send(audio_out)

    except asyncio.CancelledError:
        logging.warning("وظیفه ارسال به کلاینت لغو شد.")
    except Exception as e:
        logging.error(f"خطا در دریافت پاسخ از Gemini: {e}", exc_info=True)

async def websocket_handler(request):
    """مدیریت کامل یک اتصال WebSocket از ابتدا تا انتها."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logging.info(f"کلاینت جدید WebSocket متصل شد: {request.remote}")

    gemini_session = None
    try:
        gemini_session = await genai.aideliver.connect(
            model=MODEL_NAME,
            audio_input_format={"sample_rate_hertz": AUDIO_INPUT_SAMPLE_RATE},
            audio_output_format={"sample_rate_hertz": AUDIO_OUTPUT_SAMPLE_RATE},
        )
        logging.info("جلسه (Session) با Gemini با موفقیت ایجاد شد.")
        
        # اجرای همزمان دو وظیفه برای ارتباط دوطرفه و پایدار
        gemini_task = asyncio.create_task(forward_to_gemini(ws, gemini_session))
        client_task = asyncio.create_task(forward_to_client(ws, gemini_session))
        
        await asyncio.gather(gemini_task, client_task)

    except Exception as e:
        logging.error(f"یک خطای بحرانی در مدیریت WebSocket رخ داد: {e}", exc_info=True)
    finally:
        logging.info("شروع فرآیند بستن اتصال...")
        if gemini_session:
            gemini_session.close()
            logging.info("جلسه با Gemini بسته شد.")
        if not ws.closed:
            await ws.close()
            logging.info(f"ارتباط WebSocket با {request.remote} بسته شد.")
    
    return ws

async def http_handler(request):
    """سرو کردن فایل HTML اصلی برنامه."""
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
    logging.info(f"سرور روی http://0.0.0.0:{port} در حال اجراست...")
    logging.info("برای باز کردن برنامه، آدرس بالا را در مرورگر خود باز کنید.")
    logging.info("برای متوقف کردن سرور، کلیدهای Ctrl+C را فشار دهید.")
    
    # این خط سرور را برای همیشه در حال اجرا نگه می‌دارد تا زمانی که به صورت دستی متوقف شود
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        # نصب نیازمندی‌ها قبل از اجرا
        # دستورات زیر را در ترمینال خود اجرا کنید:
        # pip install google-generativeai aiohttp websockets
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("\nسرور توسط کاربر متوقف شد.")
    except Exception as e:
        logging.critical(f"خطای مرگبار در اجرای برنامه: {e}", exc_info=True)
