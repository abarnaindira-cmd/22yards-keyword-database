from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class ProductBase(BaseModel):
    asin: str = Field(..., min_length=1, max_length=50, description="Product ASIN")
    product_name: str = Field(..., min_length=1, max_length=500, description="Product title / name")
    category: Optional[str] = Field(default=None, max_length=100, description="Product category")
    status: Optional[str] = Field(default="pending", max_length=50, description="Collection status e.g. pending, in_progress, completed")

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    asin: Optional[str] = Field(default=None, min_length=1, max_length=50)
    product_name: Optional[str] = Field(default=None, min_length=1, max_length=500)
    category: Optional[str] = Field(default=None, max_length=100)
    status: Optional[str] = Field(default=None, max_length=50)

class ProductResponse(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ProductUploadResponse(BaseModel):
    filename: str
    total_rows: int
    imported_count: int
    skipped_count: int
    message: str
