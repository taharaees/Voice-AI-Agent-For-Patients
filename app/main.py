import logging
import hmac
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import Base, engine, get_db
from app.models import Patient  # noqa: F401 - ensure model metadata is registered
from app.routes.patients import router as patients_router
from app.schemas.patient import HealthResult, ResponseEnvelope
from app.voice.vapi import router as vapi_router
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Patient Registration API", version="1.0.0", lifespan=lifespan)
app.include_router(patients_router)
app.include_router(vapi_router)


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if settings.api_key and request.url.path.startswith("/patients"):
        expected = f"Bearer {settings.api_key}"
        if not hmac.compare_digest(request.headers.get("authorization", ""), expected):
            return JSONResponse(status_code=401, content={"data": None, "error": {"message": "Unauthorized"}})
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    details = [
        {"loc": error.get("loc", []), "msg": error.get("msg", "Invalid value"), "type": error.get("type", "value_error")}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"data": None, "error": {"message": "Request validation failed", "details": jsonable_encoder(details)}})


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request could not be completed"
    return JSONResponse(status_code=exc.status_code, content={"data": None, "error": {"message": message}})


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_: Request, exc: SQLAlchemyError):
    logging.getLogger(__name__).error("Database operation failed (exception_type=%s)", type(exc).__name__)
    return JSONResponse(status_code=500, content={"data": None, "error": {"message": "Database operation failed"}})


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception):
    logging.getLogger(__name__).error("Unhandled API error (exception_type=%s)", type(exc).__name__)
    return JSONResponse(status_code=500, content={"data": None, "error": {"message": "Internal server error"}})


@app.get("/health", response_model=ResponseEnvelope[HealthResult])
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"data": None, "error": {"message": "Database unavailable"}})
    return {"data": {"status": "ok"}, "error": None}
