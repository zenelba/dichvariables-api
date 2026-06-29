# DichVariables API

FastAPI service for analyzing dichotomous (0/1) survey data: case segmentation, hierarchical clustering (dendrograms), and distance graphs. Includes a small web UI and is deployable to Vercel.

**Production URL:** https://dichvariables-api.vercel.app

## Contents

- [Quick start](#quick-start)
- [API usage](#api-usage)
- [Single mode vs multiple mode](#single-mode-vs-multiple-mode)
- [Request payload](#request-payload)
- [Response fields](#response-fields)
- [Similarity and distance calculations](docs/STATISTICS.md)
- [Python examples](#python-examples)
- [Local development](#local-development)

## Quick start

1. Prepare an **Arrow IPC** file (`.arrow`) with binary columns and a case-weight column.
2. POST a JSON **payload** and the file to `/api/v1/analyze`.
3. Read JSON results; dendrograms include a PNG as base64.

```bash
curl -X POST "https://dichvariables-api.vercel.app/api/v1/analyze" \
  -F "payload=@payload.json" \
  -F "dataframe=@data.arrow"
```

Web UI: open `/` in a browser when the server is running.

## API usage

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check `{"status":"ok"}` |
| `GET` | `/` | Web UI |
| `POST` | `/api/v1/analyze` | Run analysis |

### `POST /api/v1/analyze`

**Content type:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `payload` | string (JSON) | Analysis configuration (see below) |
| `dataframe` | file | Arrow IPC stream/file with 0/1 data |

**Requirements:**

- At least **2 rows** (cases/observations).
- All values in entity columns are treated as binary (non-zero → 1).
- Case weights must be **non-negative** and not all zero.

### Validation errors

When columns are missing or misnamed, the API returns `422` with structured detail:

```json
{
  "detail": {
    "message": "Missing columns for pairs: ...",
    "columns_in_file": ["IM1_11_2", "wrakin2"],
    "found_pairs": [[2, 11]],
    "found_variable_ids": [2],
    "found_item_ids": [11],
    "missing_pairs": [[2, 12]]
  }
}
```

Use `found_*` fields to compare your file against the payload.

## Single mode vs multiple mode

### Single mode (`mode: "single"`)

Each **column** is one **variable**. Each **row** is one **case**.

| Concept | Description |
|---------|-------------|
| Columns | `VAR_{id}` (e.g. `VAR_1`, `VAR_2`) |
| Rows | Cases / respondents |
| Weight | One column (e.g. `wrakin1`), set via `weight_column` or last non-entity column |
| Dendrogram (`dendrogram`) | Clusters **variables** |

### Multiple mode (`mode: "multiple"`)

Each **column** is one **variable × item** pair (e.g. brand × trait). Each **row** is one **case**.

| Concept | Description |
|---------|-------------|
| Columns | `{prefix}_{item_id}_{variable_id}` (e.g. `IM1_11_2`) |
| `column_prefix` | Required prefix without underscores (e.g. `IM1`) |
| `variables` | Trait definitions (IDs used in column names) |
| `items` | Brand/subject definitions (IDs used in column names) |
| Rows | Cases / respondents |
| Weight | One column (e.g. `wrakin2`) |
| `dendrogram` | Clusters **items** (brands) |
| `dendrogram_variables` | Clusters **variables** (traits) |

**Column rule (multiple mode):**

```
{column_prefix}_{item_id}_{variable_id}
```

Example: item **11** (T-2), variable **2** (zaupanja vreden), prefix **IM1** → column **`IM1_11_2`**.

The API expects the **full cross product** of all `variables` × all `items` — one column per pair.

## Request payload

### Top-level fields

| Field | Required | Description |
|-------|----------|-------------|
| `variables` | always | Map of variable ID → `{short_description, long_description, group_id?}` |
| `mode` | always | `"single"` or `"multiple"` |
| `items` | multiple mode | Map of item ID → descriptions |
| `column_prefix` | multiple mode | Prefix for entity columns (no `_`) |
| `groups` | if `group_id` used | Map of group ID → descriptions |
| `weight_column` | optional | Name of weight column; default = last non-entity column |
| `outputs` | always | At least one output block (see below) |

### Outputs

| Output key | Applies to | Description |
|------------|------------|-------------|
| `segmentation` | both modes | Cluster cases into `num_segments` groups |
| `dendrogram` | single: variables; multiple: **items** | Hierarchical clustering + PNG |
| `dendrogram_variables` | multiple mode | Hierarchical clustering of **variables** + PNG |
| `graph` | both modes | Pairwise case distances (nodes = rows) |

Each dendrogram config:

```json
{
  "distance": "jaccard",
  "grouping": "average",
  "num_groups": 3,
  "image_width": 1200,
  "image_height": 800,
  "image_dpi": 150
}
```

- **`distance`:** `"jaccard"` or `"simpson"`
- **`grouping`:** `"ward"`, `"complete"`, or `"average"` (dendrogram linkage only)
- **`num_groups`:** Number of flat clusters for coloring / assignments
- **`image_width`:** Optional PNG width in pixels (default: 2800 via 14″ × 200 dpi)
- **`image_height`:** Optional PNG height in pixels; auto-scaled from label count if omitted
- **`image_dpi`:** PNG resolution, 72–600 (default: 200)

When both `image_width` and `image_height` are set, the PNG matches those dimensions exactly. The response includes `image_width`, `image_height`, and `image_dpi` alongside `image_png_base64`.

### Example — multiple mode

```json
{
  "variables": {
    "2": {"short_description": "Trait A", "long_description": "Trait A long"},
    "5": {"short_description": "Trait B", "long_description": "Trait B long"}
  },
  "mode": "multiple",
  "column_prefix": "IM1",
  "items": {
    "11": {"short_description": "Brand X", "long_description": "Brand X long"},
    "12": {"short_description": "Brand Y", "long_description": "Brand Y long"}
  },
  "weight_column": "wrakin2",
  "outputs": {
    "dendrogram": {
      "distance": "jaccard",
      "grouping": "average",
      "num_groups": 2
    },
    "dendrogram_variables": {
      "distance": "jaccard",
      "grouping": "average",
      "num_groups": 2
    }
  }
}
```

Required columns: `IM1_11_2`, `IM1_11_5`, `IM1_12_2`, `IM1_12_5`, `wrakin2`.

## Response fields

| Field | Content |
|-------|---------|
| `segmentation` | `{num_segments, assignments}` — row index → segment ID |
| `dendrogram` | Items (multiple) or variables (single): config, `cluster_assignments`, `image_width`, `image_height`, `image_dpi`, `image_png_base64` |
| `dendrogram_variables` | Variables (multiple mode only): same shape as `dendrogram` |
| `graph` | `{distance, nodes, edges}` — edges are pairwise case distances |

Dendrogram PNG is UTF-8 base64 in `image_png_base64`.

## Similarity and distance calculations

See **[docs/STATISTICS.md](docs/STATISTICS.md)** for:

- **When to use Jaccard vs Simpson** (decision guide and use cases)
- **How each metric is calculated** (formulas, weighted examples)
- **Worked examples** with step-by-step element distances in single mode (variables) and multiple mode (items + variables)
- How similarities apply to cases, variables, and items/brands

**Short guide:**

| Metric | Use when |
|--------|----------|
| **Jaccard** | Symmetric comparison; profiles have similar “density”; penalize differences in both presence and absence. **Default choice.** |
| **Simpson** | One profile is often a **subset** of another; you care how well the smaller profile is contained in the larger. |

Both return **distance = 1 − similarity** and respect case weights.

## Python examples

### Call API and save both dendrogram images

```python
import base64
import json
from pathlib import Path

import requests

API_URL = "https://dichvariables-api.vercel.app/api/v1/analyze"

payload = {
    "variables": {"2": {"short_description": "A", "long_description": "Trait A"}},
    "mode": "multiple",
    "column_prefix": "IM1",
    "items": {"11": {"short_description": "X", "long_description": "Brand X"}},
    "weight_column": "wrakin2",
    "outputs": {
        "dendrogram": {"distance": "jaccard", "grouping": "average", "num_groups": 2},
        "dendrogram_variables": {"distance": "jaccard", "grouping": "average", "num_groups": 2},
    },
}

with open("data.arrow", "rb") as f:
    r = requests.post(
        API_URL,
        data={"payload": json.dumps(payload)},
        files={"dataframe": ("data.arrow", f, "application/vnd.apache.arrow.stream")},
        timeout=300,
    )
r.raise_for_status()
result = r.json()

out = Path("images")
out.mkdir(exist_ok=True)

if "dendrogram" in result:
    (out / "dendrogram_items.png").write_bytes(
        base64.b64decode(result["dendrogram"]["image_png_base64"])
    )

if "dendrogram_variables" in result:
    (out / "dendrogram_variables.png").write_bytes(
        base64.b64decode(result["dendrogram_variables"]["image_png_base64"])
    )
```

### Build a minimal Arrow file (Polars)

```python
import io
import polars as pl

df = pl.DataFrame({
    "IM1_11_2": [1, 0, 1],
    "IM1_12_2": [0, 1, 0],
    "wrakin2": [1.0, 2.0, 1.5],
})
buf = io.BytesIO()
df.write_ipc(buf)
Path("data.arrow").write_bytes(buf.getvalue())
```

## Local development

```bash
pip install -r requirements.txt uvicorn polars
uvicorn backend.main:app --reload --port 8000
python smoke_test.py
```

Regenerate embedded frontend assets after editing `backend/public/*`:

```bash
python scripts/generate_frontend_assets.py
```

## Project layout

```
backend/
  main.py           FastAPI app
  models.py         Request/response schemas
  dataframe.py      Arrow parsing & column validation
  pipeline.py       Analysis orchestration
  services/         Segmentation, dendrogram, graph, distances
  public/           Web UI source
docs/
  STATISTICS.md     Similarity & distance formulas
smoke_test.py       Integration tests
```
