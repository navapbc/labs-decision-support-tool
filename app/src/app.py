from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import logging

from chainlit.utils import mount_chainlit
from src.app_config import app_config
from src.healthcheck import healthcheck_router
from src.chat_api import router as chat_router
from src.profiling import request_context, reset_request_stats

logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # Imagine LA uses port 5173 for development
    allow_origins=["http://localhost:5173"],
    allow_origin_regex=r"https://(dev-social-benefits-navigator[a-zA-Z0-9-]+|benefitnavigator)\.web\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(healthcheck_router)

@app.middleware("http")
async def profiling_middleware(request: Request, call_next):
    """Middleware to track request timing and add profiling headers"""
    reset_request_stats()  # Reset stats for new request
    
    response = await call_next(request)
    
    # Get profiling stats
    stats = request_context.get().get("stats")
    if stats:
        # Add timing headers
        for timing in stats.timings:
            response.headers[f"X-Timing-{timing['name']}"] = str(timing['duration'])
        response.headers["X-Timing-Total"] = str(stats.get_total_duration())
        
        # Log detailed stats
        logger.info("Request profiling stats:\n%s", stats.to_json())
    
    return response

if app_config.enable_chat_api:
    app.include_router(chat_router)

# Add Chainlit AFTER including routers
mount_chainlit(app=app, target="src/chainlit.py", path="/chat")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)