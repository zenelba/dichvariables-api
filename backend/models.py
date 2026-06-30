from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Mode(str, Enum):
    SINGLE = "single"
    MULTIPLE = "multiple"


class DistanceMetric(str, Enum):
    JACCARD = "jaccard"
    SIMPSON = "simpson"


class GroupingMethod(str, Enum):
    WARD = "ward"
    COMPLETE = "complete"
    AVERAGE = "average"


class DescriptionEntry(BaseModel):
    short_description: str
    long_description: str


class VariableEntry(DescriptionEntry):
    group_id: int | None = None


class SegmentationConfig(BaseModel):
    num_segments: int = Field(ge=2)


class DendrogramConfig(BaseModel):
    distance: DistanceMetric
    grouping: GroupingMethod
    num_groups: int = Field(ge=2)
    image_width: int | None = Field(
        default=None,
        ge=400,
        description="Output PNG width in pixels (default: 2800 at dpi 200)",
    )
    image_height: int | None = Field(
        default=None,
        ge=400,
        description="Output PNG height in pixels; auto from label count if omitted",
    )
    image_dpi: int = Field(
        default=200,
        ge=72,
        le=600,
        description="PNG resolution in dots per inch",
    )


class GraphConfig(BaseModel):
    distance: DistanceMetric


class AssociationsMatrixConfig(BaseModel):
    sort_by_item_id: int | None = Field(
        default=None,
        description=(
            "Item (brand) used to sort variable rows descending. "
            "Defaults to the item with the highest mean association."
        ),
    )
    image_width: int | None = Field(
        default=None,
        ge=400,
        description="Output PNG width in pixels (default: auto from brand count)",
    )
    image_height: int | None = Field(
        default=None,
        ge=400,
        description="Output PNG height in pixels (default: auto from variable count)",
    )
    image_dpi: int = Field(
        default=200,
        ge=72,
        le=600,
        description="PNG resolution in dots per inch",
    )


class OutputsConfig(BaseModel):
    segmentation: SegmentationConfig | None = None
    dendrogram: DendrogramConfig | None = None
    dendrogram_variables: DendrogramConfig | None = None
    graph: GraphConfig | None = None
    associations_matrix: AssociationsMatrixConfig | None = None

    @model_validator(mode="after")
    def at_least_one_output(self) -> "OutputsConfig":
        if not any(
            [
                self.segmentation,
                self.dendrogram,
                self.dendrogram_variables,
                self.graph,
                self.associations_matrix,
            ]
        ):
            raise ValueError("At least one output type must be requested")
        return self


class AnalyzeRequest(BaseModel):
    variables: dict[int, VariableEntry] = Field(min_length=1)
    groups: dict[int, DescriptionEntry] | None = None
    mode: Mode
    items: dict[int, DescriptionEntry] | None = None
    column_prefix: str | None = None
    weight_column: str | None = None
    outputs: OutputsConfig

    @model_validator(mode="after")
    def validate_cross_fields(self) -> "AnalyzeRequest":
        referenced_groups = {
            v.group_id for v in self.variables.values() if v.group_id is not None
        }
        if referenced_groups:
            if not self.groups:
                raise ValueError(
                    "groups is required when any variable references a group_id"
                )
            missing = referenced_groups - set(self.groups.keys())
            if missing:
                raise ValueError(
                    f"group_id(s) not found in groups: {sorted(missing)}"
                )

        if self.mode == Mode.MULTIPLE:
            if not self.items:
                raise ValueError("items is required when mode is 'multiple'")
            if not self.column_prefix or not self.column_prefix.strip():
                raise ValueError("column_prefix is required when mode is 'multiple'")
            if "_" in self.column_prefix:
                raise ValueError("column_prefix must not contain underscores")
        elif self.outputs.associations_matrix is not None:
            raise ValueError("associations_matrix output requires mode 'multiple'")
        return self


class SegmentationResult(BaseModel):
    num_segments: int
    assignments: dict[int, int]


class DendrogramResult(BaseModel):
    distance: DistanceMetric
    grouping: GroupingMethod
    num_groups: int
    color_threshold: float
    cluster_assignments: dict[int, int]
    image_width: int
    image_height: int
    image_dpi: int
    image_png_base64: str


class GraphNode(BaseModel):
    id: int


class GraphEdge(BaseModel):
    source: int
    target: int
    distance: float


class GraphResult(BaseModel):
    distance: DistanceMetric
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class AssociationsMatrixResult(BaseModel):
    variable_ids: list[int]
    item_ids: list[int]
    sort_by_item_id: int
    values: list[list[float]]
    image_width: int
    image_height: int
    image_dpi: int
    image_png_base64: str


class AnalyzeResponse(BaseModel):
    segmentation: SegmentationResult | None = None
    dendrogram: DendrogramResult | None = None
    dendrogram_variables: DendrogramResult | None = None
    graph: GraphResult | None = None
    associations_matrix: AssociationsMatrixResult | None = None

    @model_validator(mode="before")
    @classmethod
    def drop_none_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data
