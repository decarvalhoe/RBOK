from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime

app = FastAPI(
    title="Réalisons API",
    description="API pour l'assistant procédural Réalisons",
    version="0.1.0"
)

# Configuration CORS pour le développement
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend Next.js
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modèles Pydantic
class ProcedureStep(BaseModel):
    key: str
    title: str
    prompt: str
    slots: List[dict] = []

class Procedure(BaseModel):
    id: str
    name: str
    description: str
    steps: List[ProcedureStep]

class ProcedureRun(BaseModel):
    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: Optional[datetime] = None

# Stockage temporaire en mémoire (à remplacer par une vraie DB)
procedures_db = {}
runs_db = {}

@app.get("/")
def read_root():
    return {"message": "Bienvenue sur l'API de l'assistant Réalisons v0.1"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "0.1.0"}

@app.get("/procedures", response_model=List[Procedure])
def list_procedures():
    return list(procedures_db.values())

@app.post("/procedures", response_model=Procedure)
def create_procedure(procedure: Procedure):
    procedure.id = str(uuid.uuid4())
    procedures_db[procedure.id] = procedure
    return procedure

@app.get("/procedures/{procedure_id}", response_model=Procedure)
def get_procedure(procedure_id: str):
    if procedure_id not in procedures_db:
        raise HTTPException(status_code=404, detail="Procedure not found")
    return procedures_db[procedure_id]

@app.post("/runs", response_model=ProcedureRun)
def start_procedure_run(procedure_id: str, user_id: str = "default_user"):
    if procedure_id not in procedures_db:
        raise HTTPException(status_code=404, detail="Procedure not found")
    
    run = ProcedureRun(
        id=str(uuid.uuid4()),
        procedure_id=procedure_id,
        user_id=user_id,
        state="started",
        created_at=datetime.now()
    )
    runs_db[run.id] = run
    return run

@app.get("/runs/{run_id}", response_model=ProcedureRun)
def get_run(run_id: str):
    if run_id not in runs_db:
        raise HTTPException(status_code=404, detail="Run not found")
    return runs_db[run_id]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
