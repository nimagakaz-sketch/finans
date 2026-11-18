import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.config import HOST, PORT, BOT_TOKEN, UPLOAD_DIR, BASE_DIR
from backend.database import init_db
from backend.routes.expenses import router as expenses_router
from backend.routes.incomes import router as incomes_router
from backend.routes.analytics import router as analytics_router
from backend.routes.shortcuts import router as shortcuts_router
from backend.routes.family import router as family_router
from backend.bot import start_bot

bot_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    print("✅ Database initialized successfully.")

    global bot_task
    if BOT_TOKEN:
        try:
            bot_obj, dp = await start_bot()
            if bot_obj and dp:
                bot_task = asyncio.create_task(dp.start_polling(bot_obj))
        except Exception as e:
            print(f"⚠️ Failed to start bot polling: {e}")
    else:
        print("💡 BOT_TOKEN not set. Running in Web + API mode (set BOT_TOKEN in .env to activate Telegram bot).")

    yield

    # Shutdown
    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
        print("🛑 Telegram bot polling stopped.")

app = FastAPI(
    title="Family Finance Tracker API",
    description="Семейный трекер финансов и общих трат с чеками, Mini App и iOS Shortcuts",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for Telegram WebApp and iOS Shortcuts
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(expenses_router)
app.include_router(incomes_router)
app.include_router(analytics_router)
app.include_router(shortcuts_router)
app.include_router(family_router)

# Mount uploads directory for receipts
app.mount("/uploads/receipts", StaticFiles(directory=UPLOAD_DIR), name="receipts")

# Frontend directory
FRONTEND_DIR = BASE_DIR / "frontend"
if (FRONTEND_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
if (FRONTEND_DIR / "js").exists():
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")

@app.get("/")
@app.get("/webapp")
async def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Family Finance Tracker</h1>")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)
