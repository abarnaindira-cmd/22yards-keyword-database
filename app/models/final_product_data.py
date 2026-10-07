from sqlalchemy import Column, String, Text, JSON
from app.database import Base

class FinalProductData(Base):
    __tablename__ = "final_product_data"

    product_name = Column(String(500), nullable=False)
    sku_id = Column(String(50), primary_key=True, index=True)
    final_product_title = Column(Text, nullable=True)
    all_keywords = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<FinalProductData(sku_id='{self.sku_id}', product_name='{self.product_name}')>"
