from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.routers import invoices, inventory, accounts

app = FastAPI(title="erp-service")
app.include_router(invoices.router)
app.include_router(inventory.router)
app.include_router(accounts.router)

# instrument() adds middleware — must be called at module level, before the app
# starts serving. expose() adds the /metrics route. Both are safe here.
Instrumentator().instrument(app).expose(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
