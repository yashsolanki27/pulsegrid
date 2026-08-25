from fastapi import FastAPI

from app.routers import customers, orders

app = FastAPI(title="crm-service")
app.include_router(customers.router)
app.include_router(orders.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
