"""ZameenRentals — FastAPI app initialization."""
from dotenv import load_dotenv
load_dotenv()

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="ZameenRentals", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

from app.routes import router  # noqa: E402
app.include_router(router)
