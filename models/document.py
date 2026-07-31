from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models.user import User

class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    original_filename: str
    file_size: int
    file_type: str
    status: str = Field(default="uploaded")  # "uploaded", "processing", "enriched", "failed"
    
    city: str = Field(index=True)
    country: str = Field(default="Kenya")
    
    weather_data: Optional[str] = Field(default=None)
    weather_fetched_at: Optional[datetime] = None
    
    description: Optional[str] = None
    uploader_id: int = Field(foreign_key="user.id")
    uploader: "User" = Relationship(back_populates="documents")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    file_path: str

    # Exercise 2: Versioning fields
    version: int = Field(default=1)
    parent_id: Optional[int] = Field(default=None, foreign_key="document.id")

class DocumentResponse(SQLModel):
    id: int
    original_filename: str
    file_size: int
    status: str
    city: str
    country: str
    version: int
    uploaded_at: datetime