from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from thingdex.crud import ensure_root_location, get_root_location
from thingdex.db import SessionLocal
from thingdex.routes.item_types import router as item_types_router
from thingdex.routes.items import router as items_router
from thingdex.routes.labels import router as labels_router
from thingdex.routes.locations import router as locations_router
from thingdex.routes.relations import router as relations_router
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


@app.get("/health")
def health_check():
    """Simple health check for load balancers and local smoke tests."""
    root_location_id = None
    try:
        with SessionLocal() as db:
            root = get_root_location(db)
            root_location_id = str(root.id) if root else None
    except Exception:
        root_location_id = None
    return {"status": "ok", "root_location_id": root_location_id}


app.include_router(locations_router)
app.include_router(item_types_router)
app.include_router(items_router)
app.include_router(relations_router)
app.include_router(labels_router)
