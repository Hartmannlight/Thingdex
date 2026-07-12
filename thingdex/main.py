from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from thingdex.crud import ensure_root_location, get_root_location
from thingdex.db import SessionLocal
from thingdex.routes.item_types import router as item_types_router
from thingdex.routes.items import router as items_router
from thingdex.routes.label_profiles import router as label_profiles_router
from thingdex.routes.labels import router as labels_router
from thingdex.routes.locations import router as locations_router
from thingdex.routes.relations import router as relations_router
from thingdex.schemas import HealthResponse
from thingdex.validation import SchemaValidationError


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        ensure_root_location(db)
    yield

app = FastAPI(
    title="Thingdex API",
    version="0.1.0",
    description=(
        "Household inventory API. See `/docs` for interactive examples and "
        "`/openapi.json` for machine-readable specs."
    ),
    lifespan=lifespan,
)


@app.exception_handler(SchemaValidationError)
async def handle_schema_validation_error(_: Request, exc: SchemaValidationError):
    return JSONResponse(status_code=400, content={"detail": exc.errors})


def _readiness_check() -> HealthResponse:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            root = get_root_location(db)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    if root is None:
        raise HTTPException(status_code=503, detail="Root location is not initialized")
    return HealthResponse(status="ok", root_location_id=root.id)


@app.get("/health/live", response_model=HealthResponse)
def liveness_check() -> HealthResponse:
    """Report that the API process is running without probing dependencies."""
    return HealthResponse(status="ok")


@app.get("/health", response_model=HealthResponse)
@app.get("/health/ready", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Report readiness only when the database and inventory root are available."""
    return _readiness_check()


app.include_router(locations_router)
app.include_router(item_types_router)
app.include_router(items_router)
app.include_router(relations_router)
app.include_router(labels_router)
app.include_router(label_profiles_router)
