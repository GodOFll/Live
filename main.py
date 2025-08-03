import asyncio
import os
import websockets
import google.generativeai as genai
from aiohttp import web

# --- بخش تغییر یافته ---
# به جای خواندن از متغیر محیطی، کلید API را مستقیماً اینجا قرار دهید.
# هشدار: این فایل را در ریپازیتوری عمومی گیت‌هاب قرار ندهید!
api_key = "AIzaSyBoiWCq4k9w5-Uq5XtspwLylMWrrDvEE0Q" # <--- کلید API خود را اینجا بین "" کپی کنید

# بررسی اینکه آیا کلید وارد شده است یا نه
if not api_key or api_key == "YOUR_API_KEY_HERE":
    raise ValueError("لطفاً کلید API گوگل خود را در متغیر api_key قرار دهید.")

genai.configure(api_key=api_key)
# ----------------------

MODEL_NAME = "models/gemini-1.5-flash-latest"
AUDIO_INPUT_SAMPLE_RATE = 16000
AUDIO_OUTPUT_SAMPLE_RATE = 24000

print("سرور پایتون برای Gemini Live API")

# --- بقیه کد بدون تغییر باقی می‌ماند ---

async def forward_to_gemini(client_ws, gemini_session):
    print("شروع ارسال داده از کلاینت به Gemini...")
    try:
        while True:
            message = await client_ws.recv()
            if isinstance(message, str):
                await gemini_session.send_request({"text": message})
            elif isinstance(message, bytes):
                await gemini_session.send_request({"audio_in": message})
    except websockets.exceptions.ConnectionClosed as e:
        print(f"ارتباط با کلاینت قطع شد: {e}")
    except Exception as e:
        print(f"خطا در ارسال به Gemini: {e}")

async def forward_to_client(client_ws, gemini_session):
    print("شروع دریافت داده از Gemini و ارسال به کلاینت...")
    try:
        async for chunk in gemini_session.response_stream:
            if chunk.error:
                print(f"خطا از Gemini: {chunk.error}")
                await client_ws.send(f"Error: {chunk.error}")
                break
            if (text := chunk.text) and text.strip():
                await client_ws.send(f"TEXT: {text}")
            if (audio := chunk.audio_out):
                await client_ws.send(audio)
    except Exception as e:
        print(f"خطا در دریافت از Gemini: {e}")

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    print(f"کلاینت جدید WebSocket متصل شد: {request.remote}")

    gemini_session = None
    try:
        gemini_session = await genai.aideliver.connect(
            model=MODEL_NAME,
            audio_input_format={"sample_rate_hertz": AUDIO_INPUT_SAMPLE_RATE},
            audio_output_format={"sample_rate_hertz": AUDIO_OUTPUT_SAMPLE_RATE},
        )
        print("جلسه با Gemini با موفقیت ایجاد شد.")
        
        await asyncio.gather(
            forward_to_gemini(ws, gemini_session),
            forward_to_client(ws, gemini_session),
        )
    except Exception as e:
        print(f"یک خطای بحرانی در WebSocket رخ داد: {e}")
    finally:
        if gemini_session:
            gemini_session.close()
            print("جلسه با Gemini بسته شد.")
        await ws.close()
        print(f"ارتباط WebSocket با {request.remote} بسته شد.")
    
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
    print(f"سرور روی http://0.0.0.0:{port} در حال اجراست...")
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
