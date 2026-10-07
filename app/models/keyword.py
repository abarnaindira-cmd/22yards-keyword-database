from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    keyword = Column(String(255), nullable=False, index=True)
    source = Column(String(100), nullable=False, default="search_suggestions")  # e.g., 'title', 'bullet_points', 'search_suggestions'
    source_product_asin = Column(String(50), nullable=False, index=True)
    category = Column(String(100), nullable=True)
    relevance_score = Column(Float, nullable=True, default=0.0)
    marketplace = Column(String(50), nullable=False, default="amazon", index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint('keyword', 'source_product_asin', 'source', 'marketplace', name='uix_keyword_asin_source_mkt'),
    )

    def __repr__(self):
        return f"<Keyword(id={self.id}, keyword='{self.keyword}', asin='{self.source_product_asin}', source='{self.source}', marketplace='{self.marketplace}')>"
