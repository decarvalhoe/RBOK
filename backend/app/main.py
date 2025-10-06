from fastapi import FastAPI
from .api import router as api_router

app = FastAPI(title="Réalisons API", version="0.1.0")

@app.get("/")
async def root():
    return {"message": "Réalisons API v0.1 fonctionne"}

app.include_router(api_router)
