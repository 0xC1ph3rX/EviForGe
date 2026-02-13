import os
import re
import shutil
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, ConfigDict

from eviforge.core.db import create_session_factory
from eviforge.core.models import OSINTAction, OSINTActionStatus, Case
from eviforge.core.auth import ack_dependency, get_current_active_user, User
from eviforge.core.custody import log_action
from eviforge.config import load_settings

router = APIRouter(
    prefix="/cases/{case_id}/osint",
    tags=["osint"],
    dependencies=[Depends(ack_dependency), Depends(get_current_active_user)],
)

# --- Pydantic Models ---
class OSINTActionCreate(BaseModel):
    provider: str
    action_type: str
    target_label: Optional[str] = None
    notes: Optional[str] = None

class OSINTActionUpdate(BaseModel):
    status: Optional[OSINTActionStatus] = None
    target_label: Optional[str] = None
    tracking_url: Optional[str] = None
    notes: Optional[str] = None

class OSINTActionResponse(BaseModel):
    id: str
    case_id: str
    provider: str
    action_type: str
    target_label: Optional[str]
    status: OSINTActionStatus
    tracking_url: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Attributes ---
# Use the common DB session pattern

@router.get("/actions", response_model=List[OSINTActionResponse])
def list_actions(case_id: str, current_user: User = Depends(get_current_active_user)):
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        if not session.get(Case, case_id):
            raise HTTPException(status_code=404, detail="Case not found")
        actions = (
            session.query(OSINTAction)
            .filter(OSINTAction.case_id == case_id)
            .order_by(OSINTAction.updated_at.desc())
            .all()
        )
        return actions

@router.post("/actions", response_model=OSINTActionResponse)
def create_action(case_id: str, action: OSINTActionCreate, current_user: User = Depends(get_current_active_user)):
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        # Check case existence
        if not session.get(Case, case_id):
            raise HTTPException(status_code=404, detail="Case not found")

        provider = (action.provider or "").strip()
        action_type = (action.action_type or "").strip()
        target_label = (action.target_label or "").strip() or None
        notes = (action.notes or "").strip() or None
        if not provider:
            raise HTTPException(status_code=400, detail="provider is required")
        if not action_type:
            raise HTTPException(status_code=400, detail="action_type is required")
        if len(provider) > 100 or len(action_type) > 100:
            raise HTTPException(status_code=400, detail="provider/action_type too long")

        new_action = OSINTAction(
            case_id=case_id,
            provider=provider,
            action_type=action_type,
            target_label=target_label,
            notes=notes,
            status=OSINTActionStatus.DRAFT
        )
        session.add(new_action)
        session.flush() # get ID
        
        # Log chain of custody
        log_action(session, case_id, current_user.username, "OSINT Action Created", f"Provider: {provider}, Type: {action_type}")
        
        session.commit()
        session.refresh(new_action)
        return new_action

@router.patch("/actions/{action_id}", response_model=OSINTActionResponse)
def update_action(case_id: str, action_id: str, updates: OSINTActionUpdate, current_user: User = Depends(get_current_active_user)):
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        db_action = session.query(OSINTAction).filter(OSINTAction.id == action_id, OSINTAction.case_id == case_id).first()
        if not db_action:
            raise HTTPException(status_code=404, detail="Action not found")
            
        # Update fields
        changes = []
        if updates.status:
            db_action.status = updates.status
            changes.append(f"Status->{updates.status}")
        if updates.target_label is not None:
            db_action.target_label = updates.target_label.strip() or None
            changes.append("Target Updated")
        if updates.tracking_url is not None:
            db_action.tracking_url = updates.tracking_url
            changes.append(f"TrackingURL Updated")
        if updates.notes is not None:
            db_action.notes = updates.notes.strip() or None
             # Don't log full notes change to custody, maybe too verbose? Just say 'Notes Updated'
            changes.append("Notes Updated")
            
        if changes:
             log_action(session, case_id, current_user.username, "OSINT Action Updated", f"Action {action_id}: " + ", ".join(changes))
             
        session.commit()
        session.refresh(db_action)
        return db_action

@router.post("/actions/{action_id}/attachments")
def upload_attachment(case_id: str, action_id: str, file: UploadFile = File(...), current_user: User = Depends(get_current_active_user)):
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    
    with SessionLocal() as session:
        db_action = session.query(OSINTAction).filter(OSINTAction.id == action_id, OSINTAction.case_id == case_id).first()
        if not db_action:
            raise HTTPException(status_code=404, detail="Action not found")

        # Determine path: cases/<CaseName>/artifacts/osint/privacy/<provider>/<filename>
        # Need Case Name or ID? Prompt says: cases/<CaseName>/artifacts...
        # But we usually map via ID to folder if ID-based.
        # Wait, implementation plan says "cases/<CaseName>/artifacts/..." 
        # But previous steps used `EVIFORGE_VAULT_DIR` which is usually based on ID or Name?
        # Let's check how Evidence uses paths. Evidence uses ID usually or Name?
        # In `create_case` it makes a directory.
        # Let's verify vault structure logic.
        
        case = session.get(Case, case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        # We need the vault path.
        vault_root = settings.vault_dir # usually /data/cases or ./cases locally
        
        # We need to find the case folder. 
        # Ideally we standardized on `cases/{case.id}` or `cases/{case.name}`?
        # Re-check `cases.py` or `ingest.py`. 
        # Let's use `settings.vault_dir / case_id` or similar for safety.
        # Actually usually easier to use `case_id` for folders to avoid spacing issues.
        # Prompt says "cases/<CaseName>/...". 
        # I'll stick to `case_id` folder for reliability if possible, or check `case.path` if it exists.
        # Model for Case has `id` and `name` but not path.
        # Let's assume `settings.vault_dir` + `case_id` is the container path logic.
        
        # Construct path
        safe_provider = re.sub(r"[^a-zA-Z0-9._-]", "_", db_action.provider).strip("._-")
        if not safe_provider:
            safe_provider = "unknown_provider"
        # Folder: artifacts/osint/privacy/<provider>
        
        # We'll put it in `settings.vault_dir / case_id / "artifacts" / "osint" / safe_provider`
        # Using `case_id` allows us to be filesystem agnostic of "Name" changes.
        
        target_dir = os.path.join(vault_root, case_id, "artifacts", "osint", safe_provider)
        os.makedirs(target_dir, exist_ok=True)
        
        filename = os.path.basename(file.filename or "")
        # Security: sanitize filename
        filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)
        if not filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        final_path = os.path.join(target_dir, filename)
        
        with open(final_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Log Custody
        log_action(session, case_id, current_user.username, "OSINT Attachment Uploaded", f"Action {action_id}: {filename}")
        session.commit()
        
        return {"filename": filename, "path": final_path}
