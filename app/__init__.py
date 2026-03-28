"""ZameenRentals — FastAPI app initialization."""
from dotenv import load_dotenv
load_dotenv()

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="ZameenRentals", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

from app.cache import limiter as api_limiter  # noqa: E402
app.state.limiter = api_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.getLogger("zameenrentals").exception("Unhandled exception")
    return JSONResponse(status_code=500, content={"detail": "An internal error occurred."})

from app.database import init_db, close_db  # noqa: E402

@app.on_event("startup")
async def startup():
    init_db()

@app.on_event("shutdown")
async def shutdown():
    close_db()

from app.routes import router  # noqa: E402
app.include_router(router)

# Serve static files (favicon, etc.) — mounted AFTER routes so / still serves index.html
_static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
