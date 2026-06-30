"""Smoke test for the analyze endpoint."""
import base64
import io
import json
import struct
import sys

import polars as pl
import numpy as np
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def _make_ipc(df: pl.DataFrame) -> io.BytesIO:
    buf = io.BytesIO()
    df.write_ipc(buf)
    return io.BytesIO(buf.getvalue())


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_analyze_single_mode_var_columns():
    payload = {
        "variables": {
            "1": {
                "short_description": "Sp A",
                "long_description": "Species A",
                "group_id": 10,
            },
            "2": {
                "short_description": "Sp B",
                "long_description": "Species B",
            },
        },
        "groups": {
            "10": {
                "short_description": "Mammals",
                "long_description": "All mammals",
            }
        },
        "mode": "single",
        "outputs": {
            "segmentation": {"num_segments": 2},
            "dendrogram": {
                "distance": "jaccard",
                "grouping": "average",
                "num_groups": 2,
            },
            "graph": {"distance": "simpson"},
        },
    }

    df = pl.DataFrame(
        {
            "VAR_1": [1, 0, 1],
            "VAR_2": [1, 1, 0],
            "wrakin1": [1.0, 2.0, 1.5],
        }
    )

    r = client.post(
        "/api/v1/analyze",
        data={"payload": json.dumps(payload)},
        files={
            "dataframe": (
                "data.arrow",
                _make_ipc(df),
                "application/vnd.apache.arrow.stream",
            )
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "segmentation" in body
    assert "dendrogram" in body
    assert "graph" in body
    assert body["segmentation"]["num_segments"] == 2
    dendro = body["dendrogram"]
    assert "image_png_base64" in dendro
    png_bytes = base64.b64decode(dendro["image_png_base64"])
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert dendro["cluster_assignments"]
    assert len(body["graph"]["edges"]) == 3


def test_analyze_multiple_mode():
    payload = {
        "variables": {
            "1": {
                "short_description": "Trait 1",
                "long_description": "Trait one",
            },
            "2": {
                "short_description": "Trait 2",
                "long_description": "Trait two",
            },
        },
        "mode": "multiple",
        "column_prefix": "IM6",
        "items": {
            "101": {"short_description": "A", "long_description": "Brand A"},
            "102": {"short_description": "B", "long_description": "Brand B"},
        },
        "weight_column": "weight",
        "outputs": {
            "segmentation": {"num_segments": 2},
            "dendrogram": {
                "distance": "jaccard",
                "grouping": "average",
                "num_groups": 2,
            },
            "dendrogram_variables": {
                "distance": "jaccard",
                "grouping": "average",
                "num_groups": 2,
            },
            "graph": {"distance": "jaccard"},
            "brand_associations": {},
        },
    }

    df = pl.DataFrame(
        {
            "IM6_101_1": [1, 0, 1],
            "IM6_101_2": [1, 1, 0],
            "IM6_102_1": [0, 1, 1],
            "IM6_102_2": [1, 0, 0],
            "weight": [1.0, 2.0, 1.5],
        }
    )

    r = client.post(
        "/api/v1/analyze",
        data={"payload": json.dumps(payload)},
        files={
            "dataframe": (
                "data.arrow",
                _make_ipc(df),
                "application/vnd.apache.arrow.stream",
            )
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "segmentation" in body
    assert "dendrogram" in body
    assert "graph" in body
    assert body["segmentation"]["num_segments"] == 2
    dendro = body["dendrogram"]
    assert "image_png_base64" in dendro
    png_bytes = base64.b64decode(dendro["image_png_base64"])
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert set(dendro["cluster_assignments"].keys()) == {"101", "102"}
    var_dendro = body["dendrogram_variables"]
    assert "image_png_base64" in var_dendro
    var_png_bytes = base64.b64decode(var_dendro["image_png_base64"])
    assert var_png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert set(var_dendro["cluster_assignments"].keys()) == {"1", "2"}
    assert len(body["graph"]["edges"]) == 3

    assoc = body["brand_associations"]
    assert "image_png_base64" in assoc
    assoc_png = base64.b64decode(assoc["image_png_base64"])
    assert assoc_png[:8] == b"\x89PNG\r\n\x1a\n"
    assert assoc["variable_ids"] == [1, 2]
    assert assoc["item_ids"] == [101, 102]
    expected = [
        [2.5 / 4.5, 3.5 / 4.5],
        [3.0 / 4.5, 1.0 / 4.5],
    ]
    for row, exp_row in zip(assoc["values"], expected):
        for val, exp in zip(row, exp_row):
            assert abs(val - exp) < 1e-9


def test_multiple_mode_missing_column_prefix():
    payload = {
        "variables": {
            "1": {"short_description": "T", "long_description": "Trait"},
        },
        "mode": "multiple",
        "items": {
            "101": {"short_description": "A", "long_description": "Brand A"},
        },
        "outputs": {"graph": {"distance": "jaccard"}},
    }
    df = pl.DataFrame({"IM6_101_1": [1, 0], "weight": [1.0, 1.0]})

    r = client.post(
        "/api/v1/analyze",
        data={"payload": json.dumps(payload)},
        files={
            "dataframe": (
                "data.arrow",
                _make_ipc(df),
                "application/vnd.apache.arrow.stream",
            )
        },
    )
    assert r.status_code == 422


def test_multiple_mode_missing_pair_column():
    payload = {
        "variables": {
            "1": {"short_description": "T1", "long_description": "Trait one"},
            "2": {"short_description": "T2", "long_description": "Trait two"},
        },
        "mode": "multiple",
        "column_prefix": "IM6",
        "items": {
            "101": {"short_description": "A", "long_description": "Brand A"},
            "102": {"short_description": "B", "long_description": "Brand B"},
        },
        "outputs": {"graph": {"distance": "jaccard"}},
    }
    df = pl.DataFrame(
        {
            "IM6_101_1": [1, 0],
            "IM6_101_2": [0, 1],
            "IM6_102_1": [1, 0],
            "weight": [1.0, 1.0],
        }
    )

    r = client.post(
        "/api/v1/analyze",
        data={"payload": json.dumps(payload)},
        files={
            "dataframe": (
                "data.arrow",
                _make_ipc(df),
                "application/vnd.apache.arrow.stream",
            )
        },
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["found_pairs"] == [[1, 101], [1, 102], [2, 101]]
    assert detail["found_variable_ids"] == [1, 2]
    assert detail["found_item_ids"] == [101, 102]
    assert [2, 102] in detail["missing_pairs"]
    assert "columns_in_file" in detail


def test_validation_missing_groups():
    payload = {
        "variables": {
            "1": {
                "short_description": "A",
                "long_description": "B",
                "group_id": 99,
            },
        },
        "mode": "single",
        "outputs": {"graph": {"distance": "jaccard"}},
    }
    df = pl.DataFrame({"VAR_1": [1, 0], "wrakin1": [1.0, 1.0]})
    buf = io.BytesIO()
    df.write_ipc(buf)

    r = client.post(
        "/api/v1/analyze",
        data={"payload": json.dumps(payload)},
        files={
            "dataframe": (
                "data.arrow",
                io.BytesIO(buf.getvalue()),
                "application/vnd.apache.arrow.stream",
            )
        },
    )
    assert r.status_code == 422


def test_explicit_weight_column():
    payload = {
        "variables": {
            "1": {"short_description": "A", "long_description": "Alpha"},
            "2": {"short_description": "B", "long_description": "Beta"},
        },
        "mode": "single",
        "weight_column": "case_wt",
        "outputs": {
            "dendrogram": {
                "distance": "simpson",
                "grouping": "complete",
                "num_groups": 2,
            }
        },
    }
    df = pl.DataFrame(
        {
            "VAR_1": [1, 0, 1, 0],
            "VAR_2": [0, 1, 1, 0],
            "case_wt": [3.0, 1.0, 2.0, 1.0],
            "notes": ["a", "b", "c", "d"],
        }
    )

    r = client.post(
        "/api/v1/analyze",
        data={"payload": json.dumps(payload)},
        files={
            "dataframe": (
                "data.arrow",
                _make_ipc(df),
                "application/vnd.apache.arrow.stream",
            )
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dendrogram"]["distance"] == "simpson"
    png_bytes = base64.b64decode(body["dendrogram"]["image_png_base64"])
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_dendrogram_custom_image_dimensions():
    payload = {
        "variables": {
            "1": {"short_description": "A", "long_description": "Alpha"},
            "2": {"short_description": "B", "long_description": "Beta"},
        },
        "mode": "single",
        "weight_column": "wrakin1",
        "outputs": {
            "dendrogram": {
                "distance": "jaccard",
                "grouping": "average",
                "num_groups": 2,
                "image_width": 1200,
                "image_height": 800,
                "image_dpi": 150,
            }
        },
    }
    df = pl.DataFrame(
        {
            "VAR_1": [1, 0, 1],
            "VAR_2": [0, 1, 0],
            "wrakin1": [1.0, 1.0, 1.0],
        }
    )

    r = client.post(
        "/api/v1/analyze",
        data={"payload": json.dumps(payload)},
        files={
            "dataframe": (
                "data.arrow",
                _make_ipc(df),
                "application/vnd.apache.arrow.stream",
            )
        },
    )
    assert r.status_code == 200, r.text
    dendro = r.json()["dendrogram"]
    assert dendro["image_width"] == 1200
    assert dendro["image_height"] == 800
    assert dendro["image_dpi"] == 150
    png_bytes = base64.b64decode(dendro["image_png_base64"])
    assert struct.unpack(">II", png_bytes[16:24]) == (1200, 800)


def test_dendrogram_colors_match_num_groups():
    """Leaf colors must follow fcluster assignments, not scipy color_threshold."""
    n_vars = 26
    payload = {
        "variables": {
            str(i): {"short_description": f"V{i}", "long_description": f"Var {i}"}
            for i in range(1, n_vars + 1)
        },
        "mode": "single",
        "weight_column": "wrakin1",
        "outputs": {
            "dendrogram": {
                "distance": "jaccard",
                "grouping": "ward",
                "num_groups": 14,
            }
        },
    }
    rng = np.random.default_rng(42)
    cols = {f"VAR_{i}": rng.integers(0, 2, 30).tolist() for i in range(1, n_vars + 1)}
    cols["wrakin1"] = [1.0] * 30
    df = pl.DataFrame(cols)

    r = client.post(
        "/api/v1/analyze",
        data={"payload": json.dumps(payload)},
        files={
            "dataframe": (
                "data.arrow",
                _make_ipc(df),
                "application/vnd.apache.arrow.stream",
            )
        },
    )
    assert r.status_code == 200, r.text
    dendro = r.json()["dendrogram"]
    assert dendro["num_groups"] == 14
    assert len(set(dendro["cluster_assignments"].values())) == 14


def test_brand_associations_rejected_in_single_mode():
    payload = {
        "variables": {
            "1": {"short_description": "V1", "long_description": "Var 1"},
        },
        "mode": "single",
        "outputs": {"brand_associations": {}},
    }
    df = pl.DataFrame({"VAR_1": [1, 0, 1], "weight": [1.0, 1.0, 1.0]})

    r = client.post(
        "/api/v1/analyze",
        data={"payload": json.dumps(payload)},
        files={
            "dataframe": (
                "data.arrow",
                _make_ipc(df),
                "application/vnd.apache.arrow.stream",
            )
        },
    )
    assert r.status_code == 422


if __name__ == "__main__":
    test_health()
    test_analyze_single_mode_var_columns()
    test_analyze_multiple_mode()
    test_multiple_mode_missing_column_prefix()
    test_multiple_mode_missing_pair_column()
    test_validation_missing_groups()
    test_explicit_weight_column()
    test_dendrogram_custom_image_dimensions()
    test_dendrogram_colors_match_num_groups()
    test_brand_associations_rejected_in_single_mode()
    print("All smoke tests passed.")
    sys.exit(0)
