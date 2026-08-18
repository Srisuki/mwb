from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import audits, auth, dashboard, documents, masters, migrations, reports, users
from app.core.config import settings
from app.core.middleware import SecurityMiddleware
from app.db.session import engine

app = FastAPI(
    title=settings.app_name, version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(SecurityMiddleware)

for router in (
    auth.router,
    masters.router,
    audits.router,
    reports.router,
    documents.router,
    users.router,
    users.catalog_router,
    migrations.router,
    dashboard.router,
):
    app.include_router(router, prefix="/api")


@app.get("/live", tags=["health"])
def live():
    return {"status": "alive"}


@app.get("/ready", tags=["health"])
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "database": "available"}
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503, content={"status": "not_ready", "database": "unavailable"}
        )


@app.get("/health", tags=["health"])
def health():
    return ready()
