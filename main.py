from fastapi import FastAPI
from dotenv import load_dotenv
from routes.slash_command import router as slash_router
from routes.interactions import router as interactions_router

load_dotenv()

app = FastAPI(title="IR Case Name Generator")

app.include_router(slash_router)
app.include_router(interactions_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
