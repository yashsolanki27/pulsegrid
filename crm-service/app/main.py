from fastapi import FastAPI

app = FastAPI(title="crm-service")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
