import base64
import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from scipy.cluster.hierarchy import dendrogram as scipy_dendrogram
from scipy.cluster.hierarchy import fcluster, linkage

from backend.dataframe import PreparedData
from backend.models import AnalyzeRequest, DendrogramConfig, DendrogramResult
from backend.services.distances import variable_distance_condensed


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


def _render_dendrogram_png(
    linkage_matrix,
    labels: list[str],
    color_threshold: float,
    distance_name: str,
    grouping_name: str,
) -> bytes:
    fig_height = max(10, len(labels) * 0.22)
    fig, ax = plt.subplots(figsize=(14, fig_height), facecolor="white")

    dendro_preview = scipy_dendrogram(
        linkage_matrix,
        labels=labels,
        orientation="right",
        leaf_font_size=7,
        color_threshold=color_threshold,
        above_threshold_color="gray",
        no_plot=True,
    )

    scipy_dendrogram(
        linkage_matrix,
        labels=labels,
        orientation="right",
        leaf_font_size=7,
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

    ax.set_title(
        f"Hierarchical clustering of variables "
        f"(Similarity: {distance_name.upper()}, Linkage: {grouping_name.upper()})"
    )
    ax.set_ylabel(f"Distance ({distance_name.capitalize()})")
    ax.set_facecolor("white")
    ax.set_axisbelow(True)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def compute_dendrogram(
    data: PreparedData,
    request: AnalyzeRequest,
    config: DendrogramConfig,
) -> DendrogramResult:
    n_vars = len(data.entity_ids)
    if n_vars < 2:
        raise ValueError("Need at least two variables for dendrogram clustering")

    distance_vector, _similarity_pairs = variable_distance_condensed(
        data.response_matrix, data.weights, config.distance
    )
    linkage_matrix = linkage(distance_vector, method=config.grouping.value)

    threshold_idx = len(linkage_matrix) - config.num_groups
    if 0 <= threshold_idx < len(linkage_matrix):
        color_threshold = float(linkage_matrix[threshold_idx, 2])
    else:
        color_threshold = float(0.5 * linkage_matrix[-1, 2])

    flat_clusters = fcluster(
        linkage_matrix, t=config.num_groups, criterion="maxclust"
    )

    text_labels = _build_variable_labels(request, data.entity_ids)
    png_bytes = _render_dendrogram_png(
        linkage_matrix,
        text_labels,
        color_threshold,
        config.distance.value,
        config.grouping.value,
    )

    cluster_assignments = {
        data.entity_ids[i]: int(flat_clusters[i]) for i in range(n_vars)
    }

    return DendrogramResult(
        distance=config.distance,
        grouping=config.grouping,
        num_groups=config.num_groups,
        color_threshold=color_threshold,
        cluster_assignments=cluster_assignments,
        image_png_base64=base64.b64encode(png_bytes).decode("ascii"),
    )
