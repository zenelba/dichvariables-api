import io
import re
from dataclasses import dataclass

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc
from fastapi import HTTPException

from backend.models import AnalyzeRequest, Mode

VAR_COLUMN_RE = re.compile(r"^VAR_(\d+)$", re.IGNORECASE)
PLAIN_ID_RE = re.compile(r"^(\d+)$")


@dataclass
class PreparedData:
    """Parsed response table: rows=observations, columns=entity features."""

    response_matrix: np.ndarray
    weights: np.ndarray
    weight_column: str
    mode: Mode
    entity_ids: list[int]
    item_ids: list[int] | None = None
    variable_ids: list[int] | None = None
    column_pairs: list[tuple[int, int]] | None = None


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


def _multiple_column_pattern(prefix: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(prefix)}_(\d+)_(\d+)$", re.IGNORECASE)


def _parse_single_entity_id(column: str) -> int | None:
    match = VAR_COLUMN_RE.match(column)
    if match:
        return int(match.group(1))
    plain = PLAIN_ID_RE.match(column)
    if plain:
        return int(plain.group(1))
    return None


def _parse_multiple_entity_pair(
    column: str, prefix: str
) -> tuple[int, int] | None:
    match = _multiple_column_pattern(prefix).match(column)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def expected_entity_pairs(request: AnalyzeRequest) -> set[tuple[int, int]]:
    assert request.items is not None
    return {
        (var_id, item_id)
        for var_id in request.variables
        for item_id in request.items
    }


def entity_column_name(
    variable_id: int, item_id: int, prefix: str
) -> str:
    return f"{prefix}_{variable_id}_{item_id}"


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


def _prepare_single_mode(
    table: pa.Table, request: AnalyzeRequest, columns: list[str]
) -> PreparedData:
    expected = set(request.variables.keys())
    entity_cols: dict[int, str] = {}

    for col in columns:
        entity_id = _parse_single_entity_id(col)
        if entity_id is not None:
            entity_cols[entity_id] = col

    missing = expected - set(entity_cols.keys())
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing columns for IDs: {sorted(missing)} "
            f"(expected VAR_{min(missing)} format)",
        )

    extra = set(entity_cols.keys()) - expected
    if extra:
        raise HTTPException(
            status_code=422,
            detail=f"Unexpected entity columns for IDs: {sorted(extra)}",
        )

    non_entity_columns = [
        c for c in columns if _parse_single_entity_id(c) is None
    ]
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
                detail="weight_column must not be an entity (VAR_) column",
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
        weight_column=weight_column,
        mode=Mode.SINGLE,
        entity_ids=ordered_ids,
    )


def _prepare_multiple_mode(
    table: pa.Table, request: AnalyzeRequest, columns: list[str]
) -> PreparedData:
    assert request.items is not None
    assert request.column_prefix is not None

    prefix = request.column_prefix
    expected = expected_entity_pairs(request)
    entity_cols: dict[tuple[int, int], str] = {}

    for col in columns:
        pair = _parse_multiple_entity_pair(col, prefix)
        if pair is not None:
            entity_cols[pair] = col

    missing = expected - set(entity_cols.keys())
    if missing:
        example = min(missing)
        raise HTTPException(
            status_code=422,
            detail=f"Missing columns for pairs: {sorted(missing)} "
            f"(expected {entity_column_name(example[0], example[1], prefix)} format)",
        )

    extra = set(entity_cols.keys()) - expected
    if extra:
        raise HTTPException(
            status_code=422,
            detail=f"Unexpected entity columns for pairs: {sorted(extra)}",
        )

    non_entity_columns = [
        c for c in columns if _parse_multiple_entity_pair(c, prefix) is None
    ]
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
                detail="weight_column must not be an entity column",
            )
    elif non_entity_columns:
        weight_column = non_entity_columns[-1]
    else:
        raise HTTPException(
            status_code=422,
            detail="No weight column found; provide weight_column or add a trailing weight column",
        )

    ordered_pairs = sorted(expected, key=lambda p: (p[1], p[0]))
    item_ids = sorted({item_id for _, item_id in ordered_pairs})
    variable_ids = sorted(request.variables.keys())
    selected_cols = [entity_cols[pair] for pair in ordered_pairs]
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
        weight_column=weight_column,
        mode=Mode.MULTIPLE,
        entity_ids=item_ids,
        item_ids=item_ids,
        variable_ids=variable_ids,
        column_pairs=ordered_pairs,
    )


def prepare_dataframe(table: pa.Table, request: AnalyzeRequest) -> PreparedData:
    if table.num_rows == 0:
        raise HTTPException(status_code=422, detail="Dataframe must have at least one row")

    if table.num_rows < 2:
        raise HTTPException(
            status_code=422,
            detail="Need at least two observations (rows) for analysis",
        )

    columns = table.column_names
    if request.mode == Mode.SINGLE:
        return _prepare_single_mode(table, request, columns)
    return _prepare_multiple_mode(table, request, columns)
