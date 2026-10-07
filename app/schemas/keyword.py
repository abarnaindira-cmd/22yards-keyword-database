from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class KeywordBase(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=255, description="The keyword text")
    source: str = Field(default="search_suggestions", max_length=100, description="Content source e.g. title, bullet_points, search_suggestions")
    source_product_asin: str = Field(..., min_length=1, max_length=50, description="Target Product ASIN")
    category: Optional[str] = Field(default=None, max_length=100, description="Product or keyword category")
    relevance_score: Optional[float] = Field(default=0.0, ge=0.0, le=100.0, description="Relevance score (0 to 100)")

class KeywordCreate(KeywordBase):
    pass

class KeywordUpdate(BaseModel):
    keyword: Optional[str] = Field(default=None, min_length=1, max_length=255)
    source: Optional[str] = Field(default=None, max_length=100)
    source_product_asin: Optional[str] = Field(default=None, max_length=50)
    category: Optional[str] = Field(default=None, max_length=100)
    relevance_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)

class KeywordResponse(KeywordBase):
    id: int
    url_1: Optional[str] = None
    url_2: Optional[str] = None
    url_3: Optional[str] = None
    url_4: Optional[str] = None
    url_5: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
