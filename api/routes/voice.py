"""GET /api/voice/announcement (text + audio URL) and /api/voice/audio/{hash}. Session cookie required;
household comes from the session only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api import sky, voice
from api.db import get_conn
from api.session import CurrentUser, current_user

router = APIRouter()


@router.get("/api/voice/announcement")
def get_announcement(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    text = voice.announcement_text(sky.household_status(conn, user.household_id))
    result = voice.synthesize(text)
    return {
        "text": result.text,
        "audio_url": f"/api/voice/audio/{result.audio_hash}" if result.audio_hash else None,
        "source": result.source,
    }


@router.get("/api/voice/audio/{audio_hash}")
def get_audio(audio_hash: str, user: CurrentUser = Depends(current_user)) -> FileResponse:  # noqa: ARG001, B008
    path = voice.cached_audio_path(audio_hash)
    if path is None:
        raise HTTPException(status_code=404, detail="No such audio")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})
