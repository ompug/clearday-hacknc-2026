"""POST /api/receipts: upload a receipt image (raw body, image/png|jpeg|webp, at most 5 MB) and get
validated line items back for the user to confirm. Nothing is saved; the image is deleted right
after extraction (api.ai.receipts). Identity comes only from the session cookie.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from api.ai import gateway, receipts
from api.db import get_conn
from api.routes.assistant import get_llm
from api.session import CurrentUser, current_user

router = APIRouter()


async def _body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > receipts.MAX_BYTES:
        raise HTTPException(413, "too_large")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > receipts.MAX_BYTES:
            raise HTTPException(413, "too_large")
    return bytes(data)


@router.post("/api/receipts")
async def upload_receipt(
    request: Request,
    user: CurrentUser = Depends(current_user),  # noqa: B008
    conn=Depends(get_conn),  # noqa: B008
    llm: gateway.LLMClient | None = Depends(get_llm),  # noqa: B008
) -> dict:
    data = await _body(request)
    audit = gateway.Audit(conn, user.user_id, uuid.uuid4())
    try:
        # The model call blocks; keep it off the event loop.
        out = await run_in_threadpool(
            receipts.read_receipt, llm, audit, data, request.headers.get("content-type", "")
        )
        audit.write("request", "ok", fields=["image"], rows=1)
    except receipts.ReceiptError as exc:
        audit.write("request", "fallback", reason=exc.reason, fields=["image"], rows=1)
        conn.commit()
        raise HTTPException(exc.status_code, exc.reason) from exc
    conn.commit()
    return out
