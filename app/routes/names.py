"""Name generator API — serves a random pre-generated Rokugan name."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.names import SUPPORTED_GENDERS, pick_random_name

router = APIRouter()


@router.get("/api/names/random")
def random_name(gender: str = "male"):
    if gender not in SUPPORTED_GENDERS:
        return JSONResponse(
            {"error": f"gender must be one of {list(SUPPORTED_GENDERS)}"},
            status_code=400,
        )
    return JSONResponse(pick_random_name(gender))
