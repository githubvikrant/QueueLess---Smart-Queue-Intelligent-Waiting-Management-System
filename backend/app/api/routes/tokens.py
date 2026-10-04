from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import correlation_id
from app.db.session import get_db
from app.schemas.api import JoinRequest, ReassignRequest, TokenOut
from app.services import lifecycle, presenter
from app.services.publisher import publish_queue

router = APIRouter(prefix="/api/tokens", tags=["tokens"])


@router.get("/{code}", response_model=TokenOut)
def get_token(code: str, db: Session = Depends(get_db)):
    """Patient view: Q103 type karo -> counter, ETA range, reason."""
    return presenter.token_view(db, code)


@router.post("", response_model=TokenOut, status_code=201)
async def join(body: JoinRequest, db: Session = Depends(get_db), corr: str = Depends(correlation_id)):
    token = lifecycle.join_token(db, corr, **body.model_dump())
    await publish_queue(db, corr, f"{token.code} joined the queue")
    return presenter.token_view(db, token.code)


def _action(path: str, fn, reason):
    @router.post(f"/{{code}}/{path}", response_model=TokenOut, name=path)
    async def handler(code: str, db: Session = Depends(get_db), corr: str = Depends(correlation_id)):
        token = fn(db, code, corr)
        await publish_queue(db, corr, reason.format(code=token.code))
        return presenter.token_view(db, token.code)

    return handler


_action("call", lifecycle.call_token, "{code} called")
_action("start", lifecycle.start_service, "{code} service started")
_action("complete", lifecycle.complete_service, "{code} service completed")
_action("no-show", lifecycle.mark_no_show, "{code} marked no-show")
_action("skip", lifecycle.skip_token, "{code} skipped")
_action("recall", lifecycle.recall_token, "{code} recalled to waiting")


@router.post("/{code}/reassign", response_model=TokenOut)
async def reassign(code: str, body: ReassignRequest, db: Session = Depends(get_db),
                   corr: str = Depends(correlation_id)):
    """Member 1 ka Approve yahi route call karega. Eligibility DB level pe bhi check hoti hai."""
    token = lifecycle.reassign_token(db, code, body.counter_code, corr, body.reason)
    await publish_queue(db, corr, f"{token.code} reassigned to Counter {body.counter_code.upper()}")
    return presenter.token_view(db, token.code)
