from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, UniqueConstraint
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class KeywordRanking(Base):
    __tablename__ = "keyword_rankings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_product_asin = Column(String(50), nullable=False, index=True)
    keyword_id = Column(Integer, nullable=True, index=True)
    keyword = Column(String(255), nullable=False, index=True)
    result_asin = Column(String(50), nullable=False, index=True)
    rank_position = Column(Integer, nullable=False)
    result_title = Column(String(500), nullable=True)
    product_url = Column(Text, nullable=True)
    is_our_product = Column(Integer, nullable=False, default=0)
    page_number = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            'source_product_asin', 'keyword', 'result_asin',
            name='uix_ranking_source_keyword_result'
        ),
    )


class CompetitorProduct(Base):
    __tablename__ = "competitor_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_product_asin = Column(String(50), nullable=False, index=True)
    keyword_id = Column(Integer, nullable=True, index=True)
    keyword = Column(String(255), nullable=False, index=True)
    competitor_asin = Column(String(50), nullable=False, index=True)
    competitor_rank = Column(Integer, nullable=False)
    competitor_title = Column(String(500), nullable=True)
    product_url = Column(Text, nullable=True)
    price = Column(String(100), nullable=True)
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    bullet_points = Column(Text, nullable=True)
    reviews = Column(Text, nullable=True)
    marketplace = Column(String(50), nullable=False, default="amazon.in")
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            'source_product_asin', 'keyword', 'competitor_asin',
            name='uix_competitor_source_keyword_asin'
        ),
    )


class CompetitorKeyword(Base):
    __tablename__ = "competitor_keywords"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_product_asin = Column(String(50), nullable=False, index=True)
    competitor_asin = Column(String(50), nullable=False, index=True)
    source_keyword_id = Column(Integer, nullable=True, index=True)
    source_keyword = Column(String(255), nullable=True)
    keyword = Column(String(255), nullable=False, index=True)
    source = Column(String(100), nullable=False, default="amazon_suggestions")
    relevance_score = Column(Float, nullable=True, default=0.0)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            'source_product_asin', 'competitor_asin', 'keyword', 'source',
            name='uix_competitor_keyword'
        ),
    )
