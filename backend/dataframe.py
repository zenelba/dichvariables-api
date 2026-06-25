import io
import re
from dataclasses import dataclass

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc
from fastapi import HTTPException

from backend.models import AnalyzeRequest, Mode

VAR_COLUMN_RE = re.compile(r"^VAR_(\d+)$", re.IGNORECASE)
ITEM_COLUMN_RE = re.compile(r"^ITEM_(\d+)$", re.IGNORECASE)
PLAIN_ID_RE = re.compile(r"^(\d+)$")


@dataclass
class PreparedData:
    """Parsed response table: rows=observations, columns=entity ids (variables or items)."""

    response_matrix: np.ndarray
    weights: np.ndarray
    entity_ids: list[int]
    weight_column: str


def arrow_ipc_to_table(data: bytes) -> pa.Table:
    buffer = io.BytesIO(data)
    try:
        return ipc.open_stream(buffer).read_all()
    except Exception:
        buffer.seek(0)
        try:
            with ipc.open_file(buffer) as reader:
                return reader.read_all()
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid Arrow IPC dataframe: {exc}",
            ) from exc


def _entity_column_pattern(mode: Mode) -> re.Pattern[str]:
    return VAR_COLUMN_RE if mode == Mode.SINGLE else ITEM_COLUMN_RE


def _parse_entity_id(column: str, mode: Mode) -> int | None:
    pattern = _entity_column_pattern(mode)
    match = pattern.match(column)
    if match:
        return int(match.group(1))
    plain = PLAIN_ID_RE.match(column)
    if plain:
        return int(plain.group(1))
    return None


def _is_entity_column(column: str, mode: Mode) -> bool:
    return _parse_entity_id(column, mode) is not None


def expected_entity_ids(request: AnalyzeRequest) -> set[int]:
    if request.mode == Mode.SINGLE:
        return set(request.variables.keys())
    assert request.items is not None
    return set(request.items.keys())


def entity_column_name(entity_id: int, mode: Mode) -> str:
    if mode == Mode.SINGLE:
        return f"VAR_{entity_id}"
    return f"ITEM_{entity_id}"


def _column_to_float_numpy(column: pa.ChunkedArray) -> np.ndarray:
    arr = column.cast(pa.float64())
    out = np.empty(len(arr), dtype=float)
    offset = 0
    for chunk in arr.chunks:
        chunk_np = chunk.to_numpy(zero_copy_only=False)
        length = len(chunk_np)
        out[offset : offset + length] = np.nan_to_num(chunk_np, nan=0.0)
        offset += length
    return out


def prepare_dataframe(table: pa.Table, request: AnalyzeRequest) -> PreparedData:
    if table.num_rows == 0:
        raise HTTPException(status_code=422, detail="Dataframe must have at least one row")

    if table.num_rows < 2:
        raise HTTPException(
            status_code=422,
            detail="Need at least two observations (rows) for analysis",
        )

    columns = table.column_names
    expected = expected_entity_ids(request)
    entity_cols: dict[int, str] = {}

    for col in columns:
        entity_id = _parse_entity_id(col, request.mode)
        if entity_id is not None:
            entity_cols[entity_id] = col

    missing = expected - set(entity_cols.keys())
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing columns for IDs: {sorted(missing)} "
            f"(expected {entity_column_name(min(missing), request.mode)} format)",
        )

    extra = set(entity_cols.keys()) - expected
    if extra:
        raise HTTPException(
            status_code=422,
            detail=f"Unexpected entity columns for IDs: {sorted(extra)}",
        )

    non_entity_columns = [c for c in columns if not _is_entity_column(c, request.mode)]
    weight_column = request.weight_column

    if weight_column is not None:
        if weight_column not in columns:
            raise HTTPException(
                status_code=422,
                detail=f"weight_column '{weight_column}' not found in dataframe",
            )
        if weight_column in entity_cols.values():
            raise HTTPException(
                status_code=422,
                detail="weight_column must not be an entity (VAR_/ITEM_) column",
            )
    elif non_entity_columns:
        weight_column = non_entity_columns[-1]
    else:
        raise HTTPException(
            status_code=422,
            detail="No weight column found; provide weight_column or add a trailing weight column",
        )

    ordered_ids = sorted(expected)
    selected_cols = [entity_cols[i] for i in ordered_ids]
    subset = table.select(selected_cols + [weight_column])

    entity_arrays = [
        _column_to_float_numpy(subset.column(name)) for name in selected_cols
    ]
    response_matrix = np.column_stack(entity_arrays)
    response_matrix = (response_matrix != 0).astype(float)

    weights = _column_to_float_numpy(subset.column(weight_column))
    if np.any(weights < 0):
        raise HTTPException(status_code=422, detail="Weights must be non-negative")
    if np.all(weights == 0):
        raise HTTPException(status_code=422, detail="Weights must not all be zero")

    return PreparedData(
        response_matrix=response_matrix,
        weights=weights,
        entity_ids=ordered_ids,
        weight_column=weight_column,
    )
