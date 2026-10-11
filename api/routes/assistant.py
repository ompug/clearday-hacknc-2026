"""POST /api/assistant (web/lib/api/types.ts AssistantRequest -> AssistantResponse).

Natural-language split: returns a proposal for the user to confirm; nothing is saved here. Confirming
goes through POST /api/expenses, which validates the split again. Identity comes only from the session
cookie. `get_llm` is the model dependency (tests override it with a fake endpoint).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from api.ai import gateway
from api.db import get_conn
from api.session import CurrentUser, current_user

router = APIRouter()


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: str = Field(min_length=1, max_length=gateway.MESSAGE_MAX)


def get_llm() -> gateway.LLMClient | None:
    return gateway.configured_llm()


@router.post("/api/assistant")
def assistant(
    body: AssistantRequest,
    user: CurrentUser = Depends(current_user),  # noqa: B008
    conn=Depends(get_conn),  # noqa: B008
    llm: gateway.LLMClient | None = Depends(get_llm),  # noqa: B008
) -> dict:
    return gateway.assist(conn, user, body.message, llm)
