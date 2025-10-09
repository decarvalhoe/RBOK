from datetime import datetime
import uuid
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from .auth import (
    Token,
    authenticate_user,
    create_access_token,
    require_role,
)

app = FastAPI(
    title="Réalisons API",
    description=(
        "API pour l'assistant procédural Réalisons. "
        "Les opérations d'écriture nécessitent un token Bearer issu de l'endpoint ``/auth/token``. "
        "Les administrateurs peuvent créer des procédures tandis que les utilisateurs standard peuvent uniquement lancer des exécutions."
    ),
    version="0.1.0",
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
    id: Optional[str] = None
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

@app.post("/auth/token", response_model=Token, tags=["auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/procedures", response_model=Procedure, status_code=status.HTTP_201_CREATED)
def create_procedure(
    procedure: Procedure,
    current_user=Depends(require_role("admin")),
):
    procedure.id = str(uuid.uuid4())
    procedures_db[procedure.id] = procedure
    return procedure

@app.get("/procedures/{procedure_id}", response_model=Procedure)
def get_procedure(procedure_id: str):
    if procedure_id not in procedures_db:
        raise HTTPException(status_code=404, detail="Procedure not found")
    return procedures_db[procedure_id]

@app.post("/runs", response_model=ProcedureRun, status_code=status.HTTP_201_CREATED)
def start_procedure_run(
    procedure_id: str,
    current_user=Depends(require_role("user")),
):
    if procedure_id not in procedures_db:
        raise HTTPException(status_code=404, detail="Procedure not found")

    run = ProcedureRun(
        id=str(uuid.uuid4()),
        procedure_id=procedure_id,
        user_id=current_user.username,
        state="started",
        created_at=datetime.now(),
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
