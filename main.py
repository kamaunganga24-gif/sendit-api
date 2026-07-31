import os
import json
import shutil
import aiofiles
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select, or_

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from database.session import init_db, get_session
from models.user import User, UserCreate, UserResponse
from models.document import Document
from models.webhook import WebhookSubscription
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, get_current_admin, get_current_manager
)
from services.weather import get_weather, dispatch_webhook_event

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="SendIt Document Management API", version="1.0.0", lifespan=lifespan)

# Rate Limiter setup
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_FILE_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 5 * 1024 * 1024))
ALLOWED_EXTENSIONS = os.getenv("ALLOWED_EXTENSIONS", ".pdf,.jpg,.jpeg,.png,.docx").split(",")

# ==================== AUTH ENDPOINTS ====================

@app.post("/register", response_model=UserResponse, status_code=201)
def register(user_in: UserCreate, session: Session = Depends(get_session)):
    if session.exec(select(User).where(User.username == user_in.username)).first():
        raise HTTPException(400, "Username already registered")
    
    db_user = User(
        username=user_in.username,
        email=user_in.email,
        full_name=user_in.full_name,
        role=user_in.role,
        hashed_password=hash_password(user_in.password)
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(400, "Incorrect username or password")
    
    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}

# ==================== DOCUMENT ENDPOINTS ====================

@app.post("/documents/upload")
@limiter.limit("10/hour")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    city: str = Form(...),
    description: Optional[str] = Form(None),
    country: str = Form("Kenya"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file extension. Allowed: {ALLOWED_EXTENSIONS}")
    
    contents = await file.read()
    file_size = len(contents)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(400, f"File exceeds maximum allowed limit of {MAX_FILE_SIZE // (1024*1024)}MB")

    # Exercise 2: Calculate Versioning
    existing_doc = session.exec(
        select(Document)
        .where(Document.original_filename == file.filename, Document.uploader_id == current_user.id)
        .order_by(Document.version.desc())
    ).first()

    version = 1
    parent_id = None
    if existing_doc:
        version = existing_doc.version + 1
        parent_id = existing_doc.id if not existing_doc.parent_id else existing_doc.parent_id

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_v{version}_{current_user.id}_{file.filename.replace(' ', '_')}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(contents)

    doc = Document(
        filename=safe_filename,
        original_filename=file.filename,
        file_size=file_size,
        file_type=file.content_type or "application/octet-stream",
        city=city,
        country=country,
        description=description,
        uploader_id=current_user.id,
        file_path=file_path,
        status="processing",
        version=version,
        parent_id=parent_id
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    # Contextual Enrichment
    try:
        w_data = await get_weather(city, country)
        if w_data and "error" not in w_data:
            doc.weather_data = json.dumps(w_data)
            doc.weather_fetched_at = datetime.utcnow()
            doc.status = "enriched"
        else:
            doc.status = "uploaded"
        session.commit()
    except Exception:
        doc.status = "uploaded"
        session.commit()

    # Exercise 3: Dispatch Webhook
    await dispatch_webhook_event("document.uploaded", {"document_id": doc.id, "status": doc.status}, session)

    return {"message": "Upload successful", "document_id": doc.id, "version": doc.version, "status": doc.status}

# Exercise 1: Multi-filtered Search Endpoint
@app.get("/documents/search")
@limiter.limit("20/minute")
def search_documents(
    request: Request,
    q: Optional[str] = None,
    city: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    query = select(Document)

    if current_user.role not in ["admin", "manager"]:
        query = query.where(Document.uploader_id == current_user.id)

    if q:
        query = query.where(
            or_(
                Document.original_filename.contains(q),
                Document.description.contains(q)
            )
        )
    if city:
        query = query.where(Document.city == city)
    if status:
        query = query.where(Document.status == status)
    if date_from:
        query = query.where(Document.uploaded_at >= date_from)
    if date_to:
        query = query.where(Document.uploaded_at <= date_to)

    return session.exec(query).all()

@app.get("/documents")
def list_documents(
    status: Optional[str] = None,
    city: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    query = select(Document)
    if current_user.role not in ["admin", "manager"]:
        query = query.where(Document.uploader_id == current_user.id)
    if status:
        query = query.where(Document.status == status)
    if city:
        query = query.where(Document.city == city)
    return session.exec(query).all()

# Exercise 3: Webhook Registration
@app.post("/webhooks/register", status_code=201)
def register_webhook(
    url: str,
    event_type: str,
    current_user: User = Depends(get_current_admin),
    session: Session = Depends(get_session)
):
    webhook = WebhookSubscription(url=url, event_type=event_type)
    session.add(webhook)
    session.commit()
    session.refresh(webhook)
    return {"message": "Webhook registered successfully", "webhook": webhook}