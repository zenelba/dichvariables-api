from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from backend.dataframe import arrow_ipc_to_table, prepare_dataframe
from backend.models import AnalyzeRequest, AnalyzeResponse
from backend.pipeline import run_analysis

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse, response_model_exclude_none=True)
async def analyze(
    payload: str = Form(...),
    dataframe: UploadFile = File(...),
) -> AnalyzeResponse:
    try:
        request = AnalyzeRequest.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=jsonable_encoder(exc.errors())
        ) from exc

    raw = await dataframe.read()
    table = arrow_ipc_to_table(raw)
    try:
        data = prepare_dataframe(table, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return run_analysis(request, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
