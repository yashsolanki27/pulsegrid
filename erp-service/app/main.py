from fastapi import FastAPI

from app.routers import invoices, inventory, accounts

app = FastAPI(title="erp-service")
app.include_router(invoices.router)
app.include_router(inventory.router)
app.include_router(accounts.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
