from fastapi import FastAPI

from app.routers import customers

app = FastAPI(title="crm-service")
app.include_router(customers.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
