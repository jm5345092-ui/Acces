from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ModificationOut(BaseModel):
    id: str
    project_id: str
    timestamp: datetime
    file: str
    operation: str
    description: str
    before_hash: str
    after_hash: str
    before_content: str
    after_content: str
    is_binary: bool = False
    status: str

    model_config = {"from_attributes": True}


class CreateSmaliPackageRequest(BaseModel):
    operation: Literal["create_smali_package"] = "create_smali_package"
    package: str


class CreateSmaliClassRequest(BaseModel):
    operation: Literal["create_smali_class"] = "create_smali_class"
    package: str
    class_name: str
    smali_module: str | None = None  # e.g. "smali_classes3"; auto-picked if omitted


class InsertSmaliInstructionRequest(BaseModel):
    operation: Literal["insert_smali_instruction"] = "insert_smali_instruction"
    target_class: str  # e.g. "com/example/app/MainActivity" or "auto:main-activity"
    target_method: str  # e.g. "onCreate(Landroid/os/Bundle;)V"
    instruction: str
    position: Literal["start", "end"] = "start"


class ReplaceSmaliBlockRequest(BaseModel):
    operation: Literal["replace_smali_block"] = "replace_smali_block"
    target_class: str
    search_block: str
    replacement_block: str


class ModifyManifestRequest(BaseModel):
    operation: Literal["modify_manifest"] = "modify_manifest"
    xpath: str
    attribute: str
    value: str


class AddResourceRequest(BaseModel):
    operation: Literal["add_resource"] = "add_resource"
    path: str  # relative to decoded/, e.g. "assets/icons/new.png"
    content: str  # text, or base64 when is_binary=True
    is_binary: bool = False


class ApplyRequest(BaseModel):
    confirm: bool = True
