from backend.dataframe import PreparedData
from backend.models import AnalyzeRequest, AnalyzeResponse, Mode
from backend.services.associations_matrix import compute_associations_matrix
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
        skip_item_dendrogram = (
            request.mode == Mode.MULTIPLE
            and data.item_ids is not None
            and len(data.item_ids) < 2
        )
        if skip_item_dendrogram and request.outputs.dendrogram_variables is None:
            raise ValueError("Need at least two items for dendrogram clustering")
        if not skip_item_dendrogram:
            response["dendrogram"] = compute_dendrogram(
                data, request, request.outputs.dendrogram, entity="items"
            )

    if request.outputs.dendrogram_variables is not None:
        response["dendrogram_variables"] = compute_dendrogram(
            data, request, request.outputs.dendrogram_variables, entity="variables"
        )

    if request.outputs.graph is not None:
        response["graph"] = compute_graph(data, request.outputs.graph)

    if request.outputs.associations_matrix is not None:
        response["associations_matrix"] = compute_associations_matrix(
            data, request, request.outputs.associations_matrix
        )

    return AnalyzeResponse(**response)
