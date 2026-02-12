"""
FastAPI application initialization.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.endpoints import auth, documents
from app.services.user_service import initialize_user

# Initialize the FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="JWT-based authentication backend",
    version=settings.VERSION,
    docs_url=None,  # Disable Swagger UI docs
    redoc_url=None,  # Disable ReDoc docs
    openapi_url=None  # Disable OpenAPI schema endpoint
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["authentication"])
app.include_router(documents.router, prefix=f"{settings.API_V1_PREFIX}/documents", tags=["documents"])


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "Authentication API is running", "status": "healthy"}


# Initialize user data on startup
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    initialize_user()
