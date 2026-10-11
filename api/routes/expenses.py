"""POST /api/expenses and GET /api/household/members (web/lib/api/types.ts CreateExpenseRequest ->
CreateExpenseResult, HouseholdMembersResponse).

Identity comes only from the session cookie; the payer is the signed-in user. Unknown body fields
(e.g. a payer_id) are ignored. The ledger commits before the response; events and the post-commit
hook run after it.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from api import expenses, sky
from api.db import get_conn
from api.realtime import emit_all
from api.session import CurrentUser, current_user

router = APIRouter()


class Participant(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str = Field(max_length=40)
    amount_cents: StrictInt | None = None


class CreateExpenseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")  # a body payer_id/user_id is dropped, never read
    idempotency_key: str = Field(min_length=8, max_length=128)
    label: str = Field(min_length=1, max_length=200)
    total_cents: StrictInt
    split_method: str = Field(max_length=16)
    participants: list[Participant] = Field(min_length=1, max_length=20)
    due_date: dt.date | None = None


async def after_expense(outcome: expenses.ExpenseOutcome) -> None:
    """Post-commit hook for a new expense: runs after the response, never on a replay."""
    await emit_all(outcome.events)
    # Forecast refresh hook (Stream C): call it here with outcome.affected_user_ids.


@router.post("/api/expenses")
def create_expense(
    body: CreateExpenseRequest,
    background: BackgroundTasks,
    user: CurrentUser = Depends(current_user),  # noqa: B008
    conn=Depends(get_conn),  # noqa: B008
) -> dict:
    try:
        outcome = expenses.create_expense(
            conn,
            user,
            idempotency_key=body.idempotency_key,
            label=body.label,
            total_cents=body.total_cents,
            split_method=body.split_method,
            participants=[p.model_dump() for p in body.participants],
            due_on=body.due_date,
        )
    except expenses.ExpenseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if not outcome.replay:
        sky.invalidate_forecasts()
        background.add_task(after_expense, outcome)
    return outcome.result


@router.get("/api/household/members")
def household_members(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return {"members": expenses.household_members(conn, user)}
