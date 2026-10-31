import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="TaskPilot AI", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip().rstrip("/") for origin in settings.frontend_origin.split(",") if origin.strip()], allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["*"])
app.include_router(router)
