from fastapi import APIRouter, Request

router = APIRouter(tags=["meta"])


@router.get("/metrics")
def metrics(request: Request):
    return request.app.state.metrics.summary()
