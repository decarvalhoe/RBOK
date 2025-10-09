"""Environment validation helpers for the Réalisons backend."""

from __future__ import annotations

import os
from typing import Dict, List

DEFAULT_SECRET = "dev-secret-change-me"

REQUIRED_ENVIRONMENT: Dict[str, str] = {
    "REALISONS_SECRET_KEY": "JWT signing secret used to sign access tokens.",
}


def analyse_environment() -> Dict[str, List[str]]:
    """Return lists of missing or insecure variables without raising."""

    missing: List[str] = []
    insecure: List[str] = []

    secret = os.getenv("REALISONS_SECRET_KEY")
    if not secret:
        missing.append("REALISONS_SECRET_KEY")
    elif secret == DEFAULT_SECRET:
        insecure.append("REALISONS_SECRET_KEY")

    return {"missing": missing, "insecure": insecure}


def validate_environment() -> None:
    """Fail fast when critical environment variables are missing or insecure."""

    issues = analyse_environment()
    problems = []
    if issues["missing"]:
        problems.append(f"missing values: {', '.join(sorted(issues['missing']))}")
    if issues["insecure"]:
        problems.append("insecure defaults detected: " + ", ".join(sorted(issues["insecure"])))

    if problems:
        raise RuntimeError("Invalid backend configuration – " + "; ".join(problems))


def get_secret_key() -> str:
    """Return the JWT secret key, validating it in the process."""

    secret = os.getenv("REALISONS_SECRET_KEY")
    if not secret or secret == DEFAULT_SECRET:
        validate_environment()
        # validate_environment raises, so reaching here means secret is valid.
    return os.environ["REALISONS_SECRET_KEY"]
