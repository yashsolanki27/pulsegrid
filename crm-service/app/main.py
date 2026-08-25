from fastapi import FastAPI

from app.routers import customers, orders, tickets

app = FastAPI(title="crm-service")
app.include_router(customers.router)
app.include_router(orders.router)
app.include_router(tickets.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
