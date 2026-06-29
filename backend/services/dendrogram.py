import base64
import io
import struct
from typing import Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from scipy.cluster.hierarchy import dendrogram as scipy_dendrogram
from scipy.cluster.hierarchy import fcluster, linkage

from backend.dataframe import PreparedData
from backend.models import AnalyzeRequest, DendrogramConfig, DendrogramResult, Mode
from backend.services.distances import (
    item_distance_condensed,
    multiple_mode_variable_distance_condensed,
    variable_distance_condensed,
)

DendrogramEntity = Literal["items", "variables"]
LEAF_FONT_SIZE = 10.5  # 1.5× previous default of 7
CAPTION_FONT_SIZE = 8


def _build_variable_labels(request: AnalyzeRequest, variable_ids: list[int]) -> list[str]:
    labels: list[str] = []
    for var_id in variable_ids:
        var = request.variables[var_id]
        text = var.long_description or var.short_description
        if var.group_id is not None and request.groups:
            group = request.groups.get(var.group_id)
            group_label = (
                group.short_description if group else f"Group {var.group_id}"
            )
            labels.append(f"{group_label}: {text}")
        else:
            labels.append(text)
    return labels


def _build_item_labels(request: AnalyzeRequest, item_ids: list[int]) -> list[str]:
    assert request.items is not None
    labels: list[str] = []
    for item_id in item_ids:
        item = request.items[item_id]
        labels.append(item.long_description or item.short_description)
    return labels


def _png_pixel_size(png_bytes: bytes) -> tuple[int, int]:
    return struct.unpack(">II", png_bytes[16:24])


def _resolve_figure_size(
    config: DendrogramConfig, label_count: int
) -> tuple[float, float, int]:
    dpi = config.image_dpi
    fig_width = (config.image_width / dpi) if config.image_width is not None else 14.0
    if config.image_height is not None:
        fig_height = config.image_height / dpi
    else:
        fig_height = max(10.0, label_count * 0.22)
    return fig_width, fig_height, dpi


def _render_dendrogram_png(
    linkage_matrix,
    labels: list[str],
    color_threshold: float,
    distance_name: str,
    grouping_name: str,
    entity_label: str,
    config: DendrogramConfig,
) -> tuple[bytes, int, int, int]:
    fig_width, fig_height, dpi = _resolve_figure_size(config, len(labels))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), facecolor="white")
    caption = (
        f"Hierarchical clustering of {entity_label} "
        f"(Similarity: {distance_name.upper()}, Linkage: {grouping_name.upper()})"
    )

    dendro_preview = scipy_dendrogram(
        linkage_matrix,
        labels=labels,
        orientation="right",
        leaf_font_size=LEAF_FONT_SIZE,
        color_threshold=color_threshold,
        above_threshold_color="gray",
        no_plot=True,
    )

    scipy_dendrogram(
        linkage_matrix,
        labels=labels,
        orientation="right",
        leaf_font_size=LEAF_FONT_SIZE,
        color_threshold=color_threshold,
        above_threshold_color="gray",
        ax=ax,
        no_plot=False,
    )

    ordered_leaf_colors = dendro_preview.get("leaves_color_list", [])
    y_positions = sorted(ax.get_yticks())

    if y_positions and len(y_positions) == len(ordered_leaf_colors):
        row_step = y_positions[1] - y_positions[0] if len(y_positions) > 1 else 10
        band_half_height = row_step / 2
        band_start_idx = 0
        current_color = ordered_leaf_colors[0]

        for idx in range(1, len(ordered_leaf_colors) + 1):
            color_changed = (
                idx == len(ordered_leaf_colors)
                or ordered_leaf_colors[idx] != current_color
            )
            if color_changed:
                y0 = y_positions[band_start_idx] - band_half_height
                y1 = y_positions[idx - 1] + band_half_height
                ax.axhspan(
                    y0,
                    y1,
                    xmin=0,
                    xmax=1,
                    color=current_color,
                    alpha=0.18,
                    zorder=0,
                )
                if idx < len(ordered_leaf_colors):
                    band_start_idx = idx
                    current_color = ordered_leaf_colors[idx]

        for label, color in zip(ax.get_yticklabels(), ordered_leaf_colors):
            label.set_color(color)
            label.set_fontweight("bold")
            label.set_fontsize(LEAF_FONT_SIZE)

    ax.set_ylabel("")
    ax.set_facecolor("white")
    ax.set_axisbelow(True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.text(
        0.5,
        0.01,
        caption,
        ha="center",
        va="bottom",
        fontsize=CAPTION_FONT_SIZE,
        color="#555555",
    )

    buf = io.BytesIO()
    fixed_size = (
        config.image_width is not None and config.image_height is not None
    )
    if fixed_size:
        fig.savefig(buf, format="png", dpi=dpi, facecolor="white")
    else:
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    png_bytes = buf.getvalue()
    width_px, height_px = _png_pixel_size(png_bytes)
    return png_bytes, width_px, height_px, dpi


def _compute_dendrogram_from_distances(
    distance_vector,
    entity_ids: list[int],
    text_labels: list[str],
    entity_label: str,
    config: DendrogramConfig,
) -> DendrogramResult:
    n_entities = len(entity_ids)
    linkage_matrix = linkage(distance_vector, method=config.grouping.value)

    threshold_idx = len(linkage_matrix) - config.num_groups
    if 0 <= threshold_idx < len(linkage_matrix):
        color_threshold = float(linkage_matrix[threshold_idx, 2])
    else:
        color_threshold = float(0.5 * linkage_matrix[-1, 2])

    flat_clusters = fcluster(
        linkage_matrix, t=config.num_groups, criterion="maxclust"
    )

    png_bytes, width_px, height_px, dpi = _render_dendrogram_png(
        linkage_matrix,
        text_labels,
        color_threshold,
        config.distance.value,
        config.grouping.value,
        entity_label,
        config,
    )

    cluster_assignments = {
        entity_ids[i]: int(flat_clusters[i]) for i in range(n_entities)
    }

    return DendrogramResult(
        distance=config.distance,
        grouping=config.grouping,
        num_groups=config.num_groups,
        color_threshold=color_threshold,
        cluster_assignments=cluster_assignments,
        image_width=width_px,
        image_height=height_px,
        image_dpi=dpi,
        image_png_base64=base64.b64encode(png_bytes).decode("ascii"),
    )


def compute_dendrogram(
    data: PreparedData,
    request: AnalyzeRequest,
    config: DendrogramConfig,
    *,
    entity: DendrogramEntity | None = None,
) -> DendrogramResult:
    if request.mode == Mode.MULTIPLE:
        cluster_entity = entity or "items"
        if cluster_entity == "items":
            assert data.item_ids is not None
            entity_ids = data.item_ids
            if len(entity_ids) < 2:
                raise ValueError("Need at least two items for dendrogram clustering")
            distance_vector, _ = item_distance_condensed(data, config.distance)
            text_labels = _build_item_labels(request, entity_ids)
            entity_label = "items"
        else:
            assert data.variable_ids is not None
            entity_ids = data.variable_ids
            if len(entity_ids) < 2:
                raise ValueError("Need at least two variables for dendrogram clustering")
            distance_vector, _ = multiple_mode_variable_distance_condensed(
                data, config.distance
            )
            text_labels = _build_variable_labels(request, entity_ids)
            entity_label = "variables"
    else:
        entity_ids = data.entity_ids
        if len(entity_ids) < 2:
            raise ValueError("Need at least two variables for dendrogram clustering")
        distance_vector, _ = variable_distance_condensed(
            data.response_matrix, data.weights, config.distance
        )
        text_labels = _build_variable_labels(request, entity_ids)
        entity_label = "variables"

    return _compute_dendrogram_from_distances(
        distance_vector,
        entity_ids,
        text_labels,
        entity_label,
        config,
    )
