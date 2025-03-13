import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.app_config import app_config
from src.chat_api import router as chat_router
from src.db import init_db
from src.profiling import ProfilingMiddleware
from src.profiling_stats import get_profiling_stats

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Initialize database
    await init_db()
    
    # Initialize profiling stats with DB URL if configured
    db_url = os.getenv("PROFILING_DB_URL")
    if db_url:
        get_profiling_stats().db_url = db_url
        logger.info("Initialized profiling stats with DB: %s", db_url)
    
    yield
    
    # Cleanup
    stats = get_profiling_stats()
    if stats.current_window:
        stats._persist_window()  # Save any remaining stats

app = FastAPI(lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add profiling middleware
app.add_middleware(ProfilingMiddleware)

# Add routes
app.include_router(chat_router) 