import numpy as np

from backend.models import DistanceMetric


def simpson_distance_condensed(
    binary_matrix: np.ndarray, axis_weights: np.ndarray | None = None
) -> tuple[np.ndarray, list[tuple[int, int, float]]]:
    """
    Condensed Simpson distances between rows of binary_matrix.
    If axis_weights is provided (length = n_columns), columns are weighted.
    """
    n_items = binary_matrix.shape[0]
    if n_items < 2:
        return np.array([], dtype=float), []

    bool_mat = binary_matrix.astype(bool)
    if axis_weights is not None:
        w = axis_weights.astype(float)
        item_sizes = (bool_mat * w[np.newaxis, :]).sum(axis=1)
    else:
        w = None
        item_sizes = bool_mat.sum(axis=1)

    distances: list[float] = []
    similarity_pairs: list[tuple[int, int, float]] = []

    for i in range(n_items - 1):
        for j in range(i + 1, n_items):
            if w is not None:
                both = bool_mat[i] & bool_mat[j]
                intersection = float(w[both].sum())
                min_size = float(min(item_sizes[i], item_sizes[j]))
                if min_size == 0:
                    similarity = (
                        1.0
                        if item_sizes[i] == 0 and item_sizes[j] == 0
                        else 0.0
                    )
                else:
                    similarity = intersection / min_size
            else:
                min_size = min(item_sizes[i], item_sizes[j])
                if min_size == 0:
                    similarity = (
                        1.0
                        if item_sizes[i] == 0 and item_sizes[j] == 0
                        else 0.0
                    )
                else:
                    intersection = float(np.logical_and(bool_mat[i], bool_mat[j]).sum())
                    similarity = intersection / min_size

            distances.append(1.0 - similarity)
            if similarity > 0:
                similarity_pairs.append((i, j, float(similarity)))

    return np.array(distances, dtype=float), similarity_pairs


def jaccard_distance_condensed(
    binary_matrix: np.ndarray, axis_weights: np.ndarray | None = None
) -> np.ndarray:
    """Condensed Jaccard distances between rows of binary_matrix."""
    n_items = binary_matrix.shape[0]
    if n_items < 2:
        return np.array([], dtype=float)

    bool_mat = binary_matrix.astype(bool)
    if axis_weights is not None:
        w = axis_weights.astype(float)
        item_sizes = (bool_mat * w[np.newaxis, :]).sum(axis=1)
    else:
        w = None
        item_sizes = bool_mat.sum(axis=1)

    distances: list[float] = []
    for i in range(n_items - 1):
        for j in range(i + 1, n_items):
            if w is not None:
                both = bool_mat[i] & bool_mat[j]
                intersection = float(w[both].sum())
                union = float(item_sizes[i] + item_sizes[j] - intersection)
            else:
                intersection = float(np.logical_and(bool_mat[i], bool_mat[j]).sum())
                union = float(item_sizes[i] + item_sizes[j] - intersection)

            if union == 0:
                distances.append(0.0)
            else:
                distances.append(1.0 - intersection / union)

    return np.array(distances, dtype=float)


def observation_distance_condensed(
    response_matrix: np.ndarray,
    weights: np.ndarray,
    metric: DistanceMetric,
) -> np.ndarray:
    """Distances between observations (rows), using case weights."""
    n_obs, _ = response_matrix.shape
    distances: list[float] = []

    for i in range(n_obs - 1):
        for j in range(i + 1, n_obs):
            wi = weights[i] * response_matrix[i]
            wj = weights[j] * response_matrix[j]
            if metric == DistanceMetric.SIMPSON:
                intersection = float((wi * wj).sum())
                min_size = float(min(wi.sum(), wj.sum()))
                if min_size == 0:
                    similarity = 1.0 if wi.sum() == 0 and wj.sum() == 0 else 0.0
                else:
                    similarity = intersection / min_size
                distances.append(1.0 - similarity)
            else:
                intersection = float(np.minimum(wi, wj).sum())
                union = float(np.maximum(wi, wj).sum())
                if union == 0:
                    distances.append(0.0)
                else:
                    distances.append(1.0 - intersection / union)

    return np.array(distances, dtype=float)


def variable_distance_condensed(
    response_matrix: np.ndarray,
    weights: np.ndarray,
    metric: DistanceMetric,
) -> tuple[np.ndarray, list[tuple[int, int, float]]]:
    """Distances between variables (columns), weighted by observation case weights."""
    clustering_matrix = response_matrix.T
    if metric == DistanceMetric.SIMPSON:
        return simpson_distance_condensed(clustering_matrix, axis_weights=weights)
    return jaccard_distance_condensed(clustering_matrix, axis_weights=weights), []


def pairwise_distance_matrix_from_condensed(
    condensed: np.ndarray, n: int
) -> np.ndarray:
    dist = np.zeros((n, n), dtype=float)
    idx = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            dist[i, j] = condensed[idx]
            dist[j, i] = condensed[idx]
            idx += 1
    return dist
