from scipy.cluster.hierarchy import fcluster, linkage

from backend.dataframe import PreparedData
from backend.models import DistanceMetric, SegmentationConfig, SegmentationResult
from backend.services.distances import observation_distance_condensed


def compute_segmentation(
    data: PreparedData,
    config: SegmentationConfig,
    distance: DistanceMetric = DistanceMetric.JACCARD,
) -> SegmentationResult:
    condensed = observation_distance_condensed(
        data.response_matrix, data.weights, distance
    )
    linkage_matrix = linkage(condensed, method="average")
    labels = fcluster(linkage_matrix, t=config.num_segments, criterion="maxclust")

    assignments = {i: int(labels[i]) for i in range(data.response_matrix.shape[0])}
    return SegmentationResult(
        num_segments=config.num_segments,
        assignments=assignments,
    )
