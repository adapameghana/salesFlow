import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .api import admin, auth, departments, inventory, messages, orders, reports, shop
from .config import get_settings
from .database import SessionLocal
from .services.ai_parser import ollama_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="WhatsApp Order Automation (Local)",
    version="1.0.0",
    description="Locally hosted order capture, review, routing and tracking for WhatsApp orders.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, orders, messages, departments, admin, reports, inventory, shop):
    app.include_router(module.router)


@app.get("/api/health", tags=["health"])
def health():
    database = "ok"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as exc:  # report, don't crash
        database = f"error: {exc.__class__.__name__}"
    return {"status": "ok" if database == "ok" else "degraded", "database": database, "ai": ollama_status()}
