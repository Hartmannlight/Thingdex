from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LocationBase(BaseModel):
    name: str
    parent_id: UUID | None = None
    kind: str | None = None
    meta: dict[str, Any] | None = None


class LocationCreate(LocationBase):
    name: str
    label_print: LabelPrintRequest | None = None


class LocationUpdate(BaseModel):
    name: str | None = None
    parent_id: UUID | None = None
    kind: str | None = None
    meta: dict[str, Any] | None = None


class LocationOut(LocationBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class LocationPathItem(BaseModel):
    id: UUID
    name: str


class LocationTreeNode(LocationBase):
    id: UUID
    children: list["LocationTreeNode"] = Field(default_factory=list)


class ItemTypeBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    ui: dict[str, Any] | None = None
    label_template_id: str | None = None


class ItemTypeCreate(ItemTypeBase):
    name: str


class ItemTypeUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str | None = None
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    ui: dict[str, Any] | None = None
    label_template_id: str | None = None


class ItemTypeOut(ItemTypeBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    schema_: dict[str, Any] = Field(alias="schema")
    ui: dict[str, Any]


class ItemBase(BaseModel):
    location_id: UUID | None = None
    status: str | None = None
    description: str | None = None
    props: dict[str, Any] | None = None


class LabelPrintRequest(BaseModel):
    printer_id: str
    template_id: str | None = None
    return_preview: bool | None = None


class LabelPrintResult(BaseModel):
    """Result returned after Thingdex durably queues or PrintHub accepts a job."""

    status: Literal["sent", "queued"] = "sent"
    printer_id: str
    bytes_sent: int = Field(ge=0)
    preview_png_base64: str | None = None
    job_id: str | None = None
    job_state: str | None = None


class LabelProfileBase(BaseModel):
    name: str
    entity_kind: Literal["item", "location"]
    item_type_id: UUID | None = None
    location_kind: str | None = None
    template_id: str
    printer_id: str
    auto_print: bool = True
    bindings: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class LabelProfileCreate(LabelProfileBase):
    pass


class LabelProfileUpdate(BaseModel):
    name: str | None = None
    template_id: str | None = None
    printer_id: str | None = None
    auto_print: bool | None = None
    bindings: dict[str, str] | None = None
    enabled: bool | None = None


class LabelProfileOut(LabelProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class PrintIntentOut(BaseModel):
    """Operator-safe outbox state; resolved inventory variables stay internal."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    entity_kind: str
    entity_id: UUID
    entity_version: str
    template_id: str
    printer_id: str
    state: Literal["pending", "delivering", "accepted", "failed"]
    attempts: int
    next_attempt_at: datetime | None = None
    last_error: str | None = None
    printhub_job_id: str | None = None
    printhub_job_state: str | None = None
    created_at: datetime
    updated_at: datetime
    accepted_at: datetime | None = None


class SideEffectResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    requested: bool = False
    success: bool = False
    result: LabelPrintResult | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    root_location_id: UUID | None = None


class SideEffects(BaseModel):
    label_print: SideEffectResult | None = None


class LocationCreateResponse(BaseModel):
    data: LocationOut
    side_effects: SideEffects = Field(default_factory=SideEffects)


class LabelReprintRequest(BaseModel):
    printer_id: str
    template_id: str | None = None
    item_id: UUID | None = None
    location_id: UUID | None = None
    return_preview: bool | None = None


class ItemCreate(ItemBase):
    type: str | None = Field(default=None, description="Type name")
    type_id: UUID | None = Field(default=None, description="Type ID")
    label_print: LabelPrintRequest | None = None


class ItemBulkCreateItem(ItemBase):
    type: str | None = Field(default=None, description="Type name")
    type_id: UUID | None = Field(default=None, description="Type ID")


class ItemBulkCreate(BaseModel):
    items: list[ItemBulkCreateItem]


class ItemBulkUpdateItem(BaseModel):
    id: UUID
    status: str | None = None
    description: str | None = None
    props: dict[str, Any] | None = None
    source: str | None = None


class ItemBulkUpdate(BaseModel):
    items: list[ItemBulkUpdateItem]


class ItemBulkMove(BaseModel):
    item_ids: list[UUID]
    location_id: UUID


class ItemUpdate(BaseModel):
    status: str | None = None
    description: str | None = None


class ItemMove(BaseModel):
    location_id: UUID


class ItemPropsUpdate(BaseModel):
    props: dict[str, Any]
    source: str | None = None


class ItemPropsReplace(BaseModel):
    props: dict[str, Any]
    source: str | None = None


class ItemOut(ItemBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    type_id: UUID


class ItemCreateResponse(BaseModel):
    data: ItemOut
    side_effects: SideEffects = Field(default_factory=SideEffects)


class ItemDetailType(BaseModel):
    id: UUID
    name: str


class ItemDetailLocation(BaseModel):
    physical_location_id: UUID | None = None
    effective_location_id: UUID | None = None
    effective_location_path: list[LocationPathItem] | None = None


class ItemDetailOut(ItemOut):
    type: ItemDetailType
    location: ItemDetailLocation


class ItemRelationCreate(BaseModel):
    child_item_id: UUID
    relation_type: Literal["installed_in", "uses", "paired_with"]
    quantity: int | None = Field(default=None, ge=1)
    slot: str | None = None
    notes: str | None = None


class ItemRelationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int | None = Field(default=None, ge=1)
    slot: str | None = None
    notes: str | None = None


class ItemRelationDetach(BaseModel):
    location_id: UUID | None = None


class ItemRelationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    parent_item_id: UUID
    child_item_id: UUID
    relation_type: str
    active: bool
    quantity: int | None = None
    slot: str | None = None
    notes: str | None = None
    created_at: datetime


class ItemPropHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    item_id: UUID
    prop_key: str
    captured_at: datetime
    value: Any
    source: str | None = None


class ItemSnapshotCreate(BaseModel):
    kind: str
    captured_at: str | None = None
    data_text: str | None = None
    data: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class ItemSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    item_id: UUID
    kind: str
    captured_at: datetime
    data_text: str | None = None
    data: dict[str, Any] | None = None
    meta: dict[str, Any]


class SearchLocation(BaseModel):
    root_location_id: UUID
    include_descendants: bool = True


class PropsFilter(BaseModel):
    path: str
    op: Literal["==", "!=", ">", ">=", "<", "<=", "contains", "in"]
    value: Any


class SearchRequest(BaseModel):
    type: str | None = None
    location: SearchLocation | None = None
    props_filters: list[PropsFilter] | None = None
    in_use: bool | None = None
