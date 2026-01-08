from __future__ import annotations

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
    return_preview: bool | None = None


class LabelReprintRequest(BaseModel):
    printer_id: str
    item_id: UUID | None = None
    location_id: UUID | None = None
    return_preview: bool | None = None


class ItemCreate(ItemBase):
    type: str | None = Field(default=None, description="Type name")
    type_id: UUID | None = Field(default=None, description="Type ID")
    label_print: LabelPrintRequest | None = None


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
    quantity: int | None = None
    slot: str | None = None
    notes: str | None = None


class ItemRelationUpdate(BaseModel):
    active: bool


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
    created_at: str


class ItemPropHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    item_id: UUID
    prop_key: str
    captured_at: str
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
    captured_at: str
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
