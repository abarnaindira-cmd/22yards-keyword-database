from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class KeywordSearchUrl(Base):
    __tablename__ = "keyword_search_urls"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    source_product_asin = Column(String(50), nullable=False, index=True)
    keyword = Column(String(255), nullable=False, index=True)
    url_1 = Column(Text, nullable=True)
    url_2 = Column(Text, nullable=True)
    url_3 = Column(Text, nullable=True)
    url_4 = Column(Text, nullable=True)
    url_5 = Column(Text, nullable=True)
    marketplace = Column(String(50), nullable=False, default="amazon", index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint('source_product_asin', 'keyword', 'marketplace', name='uix_keyword_url_asin_kw_mkt'),
    )

    def __repr__(self):
        return f"<KeywordSearchUrl(asin='{self.source_product_asin}', keyword='{self.keyword}', marketplace='{self.marketplace}')>"
