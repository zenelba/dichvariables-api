from backend.dataframe import PreparedData
from backend.models import GraphConfig, GraphEdge, GraphNode, GraphResult
from backend.services.distances import (
    observation_distance_condensed,
    pairwise_distance_matrix_from_condensed,
)


def compute_graph(data: PreparedData, config: GraphConfig) -> GraphResult:
    condensed = observation_distance_condensed(
        data.response_matrix, data.weights, config.distance
    )
    n = data.response_matrix.shape[0]
    dist = pairwise_distance_matrix_from_condensed(condensed, n)

    nodes = [GraphNode(id=i) for i in range(n)]
    edges: list[GraphEdge] = []
    for i in range(n):
        for j in range(i + 1, n):
            edges.append(
                GraphEdge(source=i, target=j, distance=float(dist[i, j]))
            )
    return GraphResult(distance=config.distance, nodes=nodes, edges=edges)
