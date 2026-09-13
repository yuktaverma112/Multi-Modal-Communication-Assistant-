"""
backend/utils/response.py

Uniform {code, message, data} envelope for every endpoint, matching
the response shape shown in the project guide (section 10).
"""
from typing import Any


def ok(data: Any = None, message: str = "OK") -> dict:
    return {"code": 200, "message": message, "data": data}


def error(message: str, code: int = 400) -> dict:
    return {"code": code, "message": message, "data": None}
