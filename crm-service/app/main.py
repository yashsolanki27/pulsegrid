from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.routers import customers, orders, tickets


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Expose /metrics for Prometheus scraping.
    Instrumentator().instrument(app).expose(app)
    yield


app = FastAPI(title="crm-service", lifespan=lifespan)
app.include_router(customers.router)
app.include_router(orders.router)
app.include_router(tickets.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
