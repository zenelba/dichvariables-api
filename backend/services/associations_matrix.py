import base64
import io
import struct

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from backend.dataframe import PreparedData
from backend.models import AnalyzeRequest, AssociationsMatrixConfig, AssociationsMatrixResult, Mode
from backend.services.dendrogram import _build_item_labels, _build_variable_labels

VALUE_FONT_SIZE = 8
LABEL_FONT_SIZE = 9
TITLE_FONT_SIZE = 10
CAPTION_FONT_SIZE = 8
BAR_COLOR = "#1f4e79"
HEADER_COLOR = "#3366cc"
DIVIDER_COLOR = "#d0d0d0"


def _png_pixel_size(png_bytes: bytes) -> tuple[int, int]:
    return struct.unpack(">II", png_bytes[16:24])


def _resolve_figure_size(
    config: AssociationsMatrixConfig, n_vars: int, n_items: int
) -> tuple[float, float, int]:
    dpi = config.image_dpi
    if config.image_width is not None:
        fig_width = config.image_width / dpi
    else:
        fig_width = max(10.0, n_items * 2.2 + 4.0)
    if config.image_height is not None:
        fig_height = config.image_height / dpi
    else:
        fig_height = max(6.0, n_vars * 0.38 + 2.0)
    return fig_width, fig_height, dpi


def _compute_association_matrix(data: PreparedData) -> np.ndarray:
    assert data.column_pairs is not None
    assert data.variable_ids is not None
    assert data.item_ids is not None

    pair_to_col = {pair: idx for idx, pair in enumerate(data.column_pairs)}
    total_weight = float(data.weights.sum())
    n_vars = len(data.variable_ids)
    n_items = len(data.item_ids)
    matrix = np.zeros((n_vars, n_items), dtype=float)

    for vi, var_id in enumerate(data.variable_ids):
        for ii, item_id in enumerate(data.item_ids):
            col_idx = pair_to_col[(var_id, item_id)]
            column = data.response_matrix[:, col_idx]
            matrix[vi, ii] = float((data.weights * column).sum() / total_weight)

    return matrix


def _default_sort_item_id(item_ids: list[int], matrix: np.ndarray) -> int:
    col_means = matrix.mean(axis=0)
    return item_ids[int(np.argmax(col_means))]


def _resolve_sort_item_id(
    item_ids: list[int], matrix: np.ndarray, config: AssociationsMatrixConfig
) -> int:
    if config.sort_by_item_id is not None:
        if config.sort_by_item_id not in item_ids:
            raise ValueError(
                f"sort_by_item_id {config.sort_by_item_id} not found in items: {item_ids}"
            )
        return config.sort_by_item_id
    return _default_sort_item_id(item_ids, matrix)


def _sort_matrix_rows(
    matrix: np.ndarray,
    variable_ids: list[int],
    variable_labels: list[str],
    item_ids: list[int],
    sort_item_id: int,
) -> tuple[np.ndarray, list[int], list[str]]:
    sort_col_idx = item_ids.index(sort_item_id)
    order = np.argsort(-matrix[:, sort_col_idx])
    sorted_matrix = matrix[order, :]
    sorted_variable_ids = [variable_ids[i] for i in order]
    sorted_variable_labels = [variable_labels[i] for i in order]
    return sorted_matrix, sorted_variable_ids, sorted_variable_labels


def _render_association_matrix_png(
    matrix: np.ndarray,
    variable_labels: list[str],
    item_labels: list[str],
    config: AssociationsMatrixConfig,
) -> tuple[bytes, int, int, int]:
    n_vars, n_items = matrix.shape
    fig_width, fig_height, dpi = _resolve_figure_size(config, n_vars, n_items)
    fig, axes = plt.subplots(
        1,
        n_items,
        figsize=(fig_width, fig_height),
        facecolor="white",
        squeeze=False,
        sharey=True,
        gridspec_kw={"wspace": 0.08},
    )

    y_pos = np.arange(n_vars)
    bar_height = 0.72
    x_max = 100.0

    for ii in range(n_items):
        ax = axes[0, ii]
        pcts = matrix[:, ii] * 100.0
        ax.barh(
            y_pos,
            pcts,
            height=bar_height,
            color=BAR_COLOR,
            align="center",
            zorder=2,
        )
        for yi, pct in zip(y_pos, pcts):
            ax.text(
                min(pct + 1.5, x_max - 8),
                yi,
                f"{pct:.0f}%",
                va="center",
                ha="left",
                fontsize=VALUE_FONT_SIZE,
                fontweight="bold",
                color="#222222",
                clip_on=False,
            )

        ax.set_xlim(0, x_max)
        ax.set_ylim(-0.5, n_vars - 0.5)
        ax.invert_yaxis()
        ax.set_title(
            item_labels[ii],
            fontsize=TITLE_FONT_SIZE,
            color=HEADER_COLOR,
            pad=10,
            fontweight="bold",
        )
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.tick_params(axis="x", labelsize=7, colors="#666666")
        ax.grid(axis="x", color="#eeeeee", linewidth=0.8, zorder=0)

        if ii == 0:
            ax.set_yticks(y_pos)
            ax.set_yticklabels(variable_labels, fontsize=LABEL_FONT_SIZE, color="#333333")
        else:
            ax.set_yticklabels([])
            ax.tick_params(axis="y", length=0)

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(ii == 0)
        ax.spines["bottom"].set_color(DIVIDER_COLOR)

        if ii < n_items - 1:
            ax.axvline(x=x_max, color=DIVIDER_COLOR, linewidth=1.0, zorder=3)

    fig.suptitle(
        "Brand associations (weighted % of cases)",
        fontsize=CAPTION_FONT_SIZE + 1,
        color="#555555",
        y=0.995,
    )

    fixed_size = config.image_width is not None and config.image_height is not None
    buf = io.BytesIO()
    if fixed_size:
        fig.savefig(buf, format="png", dpi=dpi, facecolor="white")
    else:
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    png_bytes = buf.getvalue()
    width_px, height_px = _png_pixel_size(png_bytes)
    return png_bytes, width_px, height_px, dpi


def compute_associations_matrix(
    data: PreparedData,
    request: AnalyzeRequest,
    config: AssociationsMatrixConfig,
) -> AssociationsMatrixResult:
    if request.mode != Mode.MULTIPLE:
        raise ValueError("associations_matrix output requires mode 'multiple'")
    assert data.variable_ids is not None
    assert data.item_ids is not None

    matrix = _compute_association_matrix(data)
    variable_labels = _build_variable_labels(request, data.variable_ids)
    item_labels = _build_item_labels(request, data.item_ids)
    sort_item_id = _resolve_sort_item_id(data.item_ids, matrix, config)

    sorted_matrix, sorted_variable_ids, sorted_variable_labels = _sort_matrix_rows(
        matrix,
        data.variable_ids,
        variable_labels,
        data.item_ids,
        sort_item_id,
    )

    png_bytes, width_px, height_px, dpi = _render_association_matrix_png(
        sorted_matrix,
        sorted_variable_labels,
        item_labels,
        config,
    )

    values = [
        [float(sorted_matrix[vi, ii]) for ii in range(len(data.item_ids))]
        for vi in range(len(sorted_variable_ids))
    ]

    return AssociationsMatrixResult(
        variable_ids=sorted_variable_ids,
        item_ids=data.item_ids,
        sort_by_item_id=sort_item_id,
        values=values,
        image_width=width_px,
        image_height=height_px,
        image_dpi=dpi,
        image_png_base64=base64.b64encode(png_bytes).decode("ascii"),
    )
