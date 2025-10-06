#!/usr/bin/env python3
"""
AI Gateway: point d’entrée pour les fonctions ASR/TTS/LLM.

- expose des endpoints HTTP (ou gRPC) pour le front/back.
- orchestre la reconnaissance vocale, la synthèse vocale et l’appel au LLM.
- implémente des tools restreints: get_required_slots, validate_slot, commit_step, etc.
"""
from fastapi import FastAPI

app = FastAPI(title="Réalisons AI Gateway", version="0.1.0")

@app.get("/")
async def root():
    return {"message": "AI Gateway opérationnel"}
