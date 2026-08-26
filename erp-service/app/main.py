from fastapi import FastAPI

from app.routers import invoices, inventory

app = FastAPI(title="erp-service")
app.include_router(invoices.router)
app.include_router(inventory.router)
# accounts router: BLOCKED — see blocked.md


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
