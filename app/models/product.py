from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    asin = Column(String(50), nullable=False, unique=True, index=True)
    product_name = Column(String(500), nullable=False, index=True)
    category = Column(String(100), nullable=True, index=True)
    status = Column(String(50), nullable=False, default="pending", index=True)  # pending, in_progress, completed
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    def __repr__(self):
        return f"<Product(id={self.id}, asin='{self.asin}', name='{self.product_name}', status='{self.status}')>"
