import base64
import io
import struct

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from backend.dataframe import PreparedData
from backend.models import AnalyzeRequest, BrandAssociationsConfig, BrandAssociationsResult, Mode
from backend.services.dendrogram import _build_item_labels, _build_variable_labels

VALUE_FONT_SIZE = 8
LABEL_FONT_SIZE = 9
TITLE_FONT_SIZE = 10
CAPTION_FONT_SIZE = 8


def _png_pixel_size(png_bytes: bytes) -> tuple[int, int]:
    return struct.unpack(">II", png_bytes[16:24])


def _resolve_figure_size(
    config: BrandAssociationsConfig, n_vars: int, n_items: int
) -> tuple[float, float, int]:
    dpi = config.image_dpi
    if config.image_width is not None:
        fig_width = config.image_width / dpi
    else:
        fig_width = max(8.0, n_items * 1.4 + 3.0)
    if config.image_height is not None:
        fig_height = config.image_height / dpi
    else:
        fig_height = max(6.0, n_vars * 0.55 + 2.5)
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


def _render_association_matrix_png(
    matrix: np.ndarray,
    variable_labels: list[str],
    item_labels: list[str],
    config: BrandAssociationsConfig,
) -> tuple[bytes, int, int, int]:
    n_vars, n_items = matrix.shape
    fig_width, fig_height, dpi = _resolve_figure_size(config, n_vars, n_items)
    fig, axes = plt.subplots(
        n_vars,
        n_items,
        figsize=(fig_width, fig_height),
        facecolor="white",
        squeeze=False,
        gridspec_kw={"wspace": 0.35, "hspace": 0.45},
    )

    bar_color = "#4C78A8"
    max_value = max(float(matrix.max()), 0.01)

    for vi in range(n_vars):
        for ii in range(n_items):
            ax = axes[vi, ii]
            value = float(matrix[vi, ii])
            pct = value * 100.0
            ax.bar([0], [value], width=0.65, color=bar_color, zorder=2)
            ax.set_xlim(-0.5, 0.5)
            ax.set_ylim(0, max(max_value * 1.15, 0.05))
            ax.set_xticks([])
            ax.set_yticks([])
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["bottom"].set_visible(False)
            if vi < n_vars - 1:
                ax.spines["left"].set_visible(False)
            ax.text(
                0,
                value + max_value * 0.03,
                f"{pct:.0f}%",
                ha="center",
                va="bottom",
                fontsize=VALUE_FONT_SIZE,
                fontweight="bold",
                color="#222222",
            )
            if vi == 0:
                ax.set_title(
                    item_labels[ii],
                    fontsize=TITLE_FONT_SIZE,
                    pad=6,
                    color="#333333",
                )
            if ii == 0:
                ax.set_ylabel(
                    variable_labels[vi],
                    fontsize=LABEL_FONT_SIZE,
                    rotation=0,
                    ha="right",
                    va="center",
                    labelpad=28,
                    color="#333333",
                )

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


def compute_brand_associations(
    data: PreparedData,
    request: AnalyzeRequest,
    config: BrandAssociationsConfig,
) -> BrandAssociationsResult:
    if request.mode != Mode.MULTIPLE:
        raise ValueError("brand_associations output requires mode 'multiple'")
    assert data.variable_ids is not None
    assert data.item_ids is not None

    matrix = _compute_association_matrix(data)
    variable_labels = _build_variable_labels(request, data.variable_ids)
    item_labels = _build_item_labels(request, data.item_ids)

    png_bytes, width_px, height_px, dpi = _render_association_matrix_png(
        matrix,
        variable_labels,
        item_labels,
        config,
    )

    values = [[float(matrix[vi, ii]) for ii in range(len(data.item_ids))] for vi in range(len(data.variable_ids))]

    return BrandAssociationsResult(
        variable_ids=data.variable_ids,
        item_ids=data.item_ids,
        values=values,
        image_width=width_px,
        image_height=height_px,
        image_dpi=dpi,
        image_png_base64=base64.b64encode(png_bytes).decode("ascii"),
    )
