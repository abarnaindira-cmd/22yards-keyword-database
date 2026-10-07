from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, test_db_connection, test_flipkart_db_connection
from app.routers.keywords import router as keywords_router
from app.routers.products import router as products_router
from app.routers.competitors import router as competitors_router
from app.routers.flipkart import router as flipkart_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database tables
    init_db()
    yield
    # Shutdown

app = FastAPI(
    title="Amazon Keyword Analysis API",
    description="Phase 1: Foundation and MySQL Database Setup - Strict Batch Validation & Persistent Tracking",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(keywords_router)
app.include_router(products_router)
app.include_router(competitors_router)
app.include_router(flipkart_router)

@app.get("/health", tags=["Health"])
def health_check():
    """Simple health-check endpoint returning system and DB status."""
    amazon_db = test_db_connection()
    flipkart_db = test_flipkart_db_connection()
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "amazon_database": amazon_db,
        "flipkart_database": flipkart_db
    }
