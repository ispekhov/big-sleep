"""Visual search endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas import SearchResponse
from ..search import SearchService

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def visual_search(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> SearchResponse:
    """Upload a photo and get ranked product matches with confidence scores."""
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty image upload")
    try:
        return SearchService(session).search(data)
    except Exception as exc:  # malformed image, etc.
        raise HTTPException(422, f"Could not process image: {exc}") from exc
