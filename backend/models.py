from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any

# ============================================================================
# Authentication Models
# ============================================================================

class LoginRequest(BaseModel):
    email: EmailStr

class UserInfo(BaseModel):
    email: str
    orcid: str
    name: str
    projects: List[str]

class LoginResponse(BaseModel):
    success: bool
    user: Optional[UserInfo] = None
    message: Optional[str] = None
    session_token: Optional[str] = None

# ============================================================================
# Synthesis Models
# ============================================================================

class SynthesisFieldsResponse(BaseModel):
    categories: Dict[str, Dict[str, List[str]]]

class ParentCandidate(BaseModel):
    unique_id: str
    sample_name: str
    sample_type: Optional[str] = None
    date_created: Optional[str] = None
    description: Optional[str] = None

class AmbiguousParent(BaseModel):
    """A parent reference matching several samples; the user must pick one."""
    row: int
    sample_name: Optional[str] = None
    field: str
    field_label: str
    reference: str
    candidates: List[ParentCandidate]

class UnresolvedParent(BaseModel):
    """A parent reference matching no sample of the expected type."""
    row: int
    sample_name: Optional[str] = None
    field: str
    field_label: str
    reference: str
    expected_type: str

class DuplicateName(BaseModel):
    row: int
    sample_name: str
    existing_count: int
    existing_ids: List[str]

class ParentSelection(BaseModel):
    row: int
    field: str
    unique_id: str

class SynthesisUploadRequest(BaseModel):
    email: str
    orcid: str
    user_name: str
    project: str
    category: str
    synthesis_type: str
    data: List[Dict[str, Any]]
    session_name: Optional[str] = None
    # Set by the client after the user resolves an earlier validation response.
    parent_selections: List[ParentSelection] = []
    confirm_duplicate_names: bool = False

class SynthesisUploadResponse(BaseModel):
    success: bool
    message: str
    summary: Optional[Dict[str, Any]] = None
    # Populated when validation halted the upload before anything was written.
    needs_selection: List[AmbiguousParent] = []
    unresolved_parents: List[UnresolvedParent] = []
    duplicate_names: List[DuplicateName] = []
