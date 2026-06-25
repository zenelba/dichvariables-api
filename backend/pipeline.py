from backend.dataframe import PreparedData
from backend.models import AnalyzeRequest, AnalyzeResponse
from backend.services.dendrogram import compute_dendrogram
from backend.services.graph import compute_graph
from backend.services.segmentation import compute_segmentation


def run_analysis(request: AnalyzeRequest, data: PreparedData) -> AnalyzeResponse:
    response: dict = {}

    if request.outputs.segmentation is not None:
        response["segmentation"] = compute_segmentation(
            data, request.outputs.segmentation
        )

    if request.outputs.dendrogram is not None:
        response["dendrogram"] = compute_dendrogram(
            data, request, request.outputs.dendrogram
        )

    if request.outputs.graph is not None:
        response["graph"] = compute_graph(data, request.outputs.graph)

    return AnalyzeResponse(**response)
