"""
FastAPI application initialization.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logger import logger, configure_logging
from app.api.v1.endpoints import auth, documents, entities, graph
from app.services.user_service import initialize_user
from app.services.neo4j_service import Neo4jService

# Configure logging
configure_logging()

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
app.include_router(entities.router, prefix=f"{settings.API_V1_PREFIX}/entities", tags=["entities"])
app.include_router(graph.router, prefix=f"{settings.API_V1_PREFIX}/graph", tags=["graph"])


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "Authentication API is running", "status": "healthy"}


def get_neo4j_service() -> Neo4jService | None:
    """Return the Neo4j service instance from app.state (for use outside request context)."""
    return getattr(app.state, "neo4j_service", None)


# Initialize user data and Neo4j on startup
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    logger.info("Starting up application...")
    logger.info(f"Project: {settings.PROJECT_NAME} v{settings.VERSION}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(f"Allowed origins: {settings.allowed_origins_list}")
    initialize_user()
    try:
        neo4j = Neo4jService()
        if neo4j.health_check():
            app.state.neo4j_service = neo4j
            logger.success("Neo4j connected")
        else:
            app.state.neo4j_service = None
            logger.warning("Neo4j health check failed; graph persistence disabled")
    except Exception as e:
        logger.warning("Neo4j not available; graph persistence disabled", error=str(e))
        app.state.neo4j_service = None
    logger.success("Application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Close connections on shutdown."""
    neo4j = getattr(app.state, "neo4j_service", None)
    if neo4j:
        neo4j.close()
        logger.info("Neo4j connection closed")
