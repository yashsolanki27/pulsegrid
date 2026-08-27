from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.routers import invoices, inventory, accounts


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Expose /metrics for Prometheus scraping.
    Instrumentator().instrument(app).expose(app)
    yield


app = FastAPI(title="erp-service", lifespan=lifespan)
app.include_router(invoices.router)
app.include_router(inventory.router)
app.include_router(accounts.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
