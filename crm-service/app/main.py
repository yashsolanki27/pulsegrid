from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.routers import customers, orders, tickets

app = FastAPI(title="crm-service")
app.include_router(customers.router)
app.include_router(orders.router)
app.include_router(tickets.router)

# instrument() adds middleware — must be called at module level, before the app
# starts serving. expose() adds the /metrics route. Both are safe here.
Instrumentator().instrument(app).expose(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
