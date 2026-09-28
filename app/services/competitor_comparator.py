import json
import re
from typing import Dict, List, Set, Any, Optional
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.keyword import Keyword
from app.models.competitor import CompetitorProduct, CompetitorKeyword

# Incomplete fragment words or structural junk to filter out
FRAGMENT_PREFIXES = {
    "made from", "have super", "glass height", "belt size", "ideal for",
    "with ergonomic", "top class", "easy to", "wear without", "waterproof head",
    "eye to", "and ear", "with adjustable", "integrating nose", "softer than"
}

NOISE_WORDS = {
    "and", "or", "for", "with", "the", "in", "on", "at", "to", "from", "by", "of",
    "is", "are", "be", "this", "that", "its", "it", "all", "any", "can", "has",
    "have", "had", "not", "but", "very", "also", "just", "about", "into", "over",
    "such", "than", "other", "some", "only", "more", "most", "no", "out", "up",
    "so", "as", "how", "what", "when", "where", "who", "which", "why", "brand",
    "best", "good", "great", "product", "quality", "buy", "purchase", "seller",
    "amazon", "item", "inch", "size", "pcs", "pack", "set", "combo"
}


def normalize_phrase(text: str) -> str:
    """Clean and normalize keyword text for comparison."""
    if not text:
        return ""
    t = text.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def tokenize_text(text: str) -> Set[str]:
    """Tokenize text into lowercase meaningful word set."""
    norm = normalize_phrase(text)
    words = norm.split()
    return {w for w in words if len(w) > 1 and not w.isdigit() and w not in NOISE_WORDS}


def is_relevant_keyword(keyword: str, category: Optional[str] = None) -> bool:
    """Filter out non-descriptive, incomplete, or generic noise fragments."""
    norm = normalize_phrase(keyword)
    if not norm or len(norm) < 3:
        return False

    # Check fragment prefixes
    for prefix in FRAGMENT_PREFIXES:
        if norm.startswith(prefix):
            return False

    words = norm.split()
    # Require 2 to 6 words
    if not (2 <= len(words) <= 6):
        return False

    # Filter out standalone numbers or single-character junk
    meaningful = [w for w in words if len(w) > 1 and not w.isdigit() and w not in NOISE_WORDS]
    if len(meaningful) < 2:
        return False

    # Ignore pure dimension/measurement numbers
    if re.search(r"\b\d+\s*(cm|mm|inch|inches|g|kg|m|ml|l)\b", norm):
        return False

    return True


def compare_product_against_competitors(db: Session, source_product_asin: str) -> Dict[str, Any]:
    """
    Compare own product details & keywords against competitor listings & keywords in MySQL.
    Identifies covered keywords and missing high-relevance competitor keywords.
    """
    product = db.query(Product).filter(Product.asin == source_product_asin).first()
    if not product:
        return {"error": f"Source product ASIN '{source_product_asin}' not found in DB"}

    # Own keywords from MySQL
    own_keyword_objs = db.query(Keyword).filter(Keyword.source_product_asin == source_product_asin).all()
    own_keywords = [k.keyword for k in own_keyword_objs]

    # Build token set of own product representation (Title + Category + Own Keywords)
    own_full_text = f"{product.product_name} {product.category or ''} " + " ".join(own_keywords)
    own_tokens = tokenize_text(own_full_text)

    # Own normalized phrase lookup
    own_phrases_norm = {normalize_phrase(k) for k in own_keywords if k}
    own_title_norm = normalize_phrase(product.product_name)

    # Competitor products from MySQL
    competitor_prods = db.query(CompetitorProduct).filter(
        CompetitorProduct.source_product_asin == source_product_asin
    ).order_by(CompetitorProduct.competitor_rank.asc()).all()

    # Competitor extracted keywords from MySQL
    competitor_kw_objs = db.query(CompetitorKeyword).filter(
        CompetitorKeyword.source_product_asin == source_product_asin
    ).all()

    raw_comp_keywords = [ck.keyword for ck in competitor_kw_objs]

    # Extract additional candidate keywords from competitor titles if needed
    for cp in competitor_prods:
        if cp.competitor_title:
            title_norm = normalize_phrase(cp.competitor_title)
            # Add title clean phrases
            title_words = title_norm.split()
            if len(title_words) >= 2:
                for i in range(len(title_words) - 1):
                    bigram = f"{title_words[i]} {title_words[i+1]}"
                    if bigram not in raw_comp_keywords:
                        raw_comp_keywords.append(bigram)

    # Filter and deduplicate competitor keywords
    filtered_comp_keywords: List[str] = []
    seen_norm = set()

    for kw in raw_comp_keywords:
        n_kw = normalize_phrase(kw)
        if n_kw not in seen_norm and is_relevant_keyword(kw, product.category):
            seen_norm.add(n_kw)
            filtered_comp_keywords.append(kw)

    covered_keywords: List[Dict[str, str]] = []
    missing_keywords: List[Dict[str, Any]] = []

    for kw in filtered_comp_keywords:
        kw_norm = normalize_phrase(kw)
        kw_tokens = tokenize_text(kw)

        # Coverage check: exact phrase match, title substring match, or 80%+ token overlap
        is_exact = (kw_norm in own_phrases_norm) or (kw_norm in own_title_norm) or (own_title_norm in kw_norm)
        token_overlap = len(kw_tokens.intersection(own_tokens)) / len(kw_tokens) if kw_tokens else 0.0

        if is_exact or token_overlap >= 0.75:
            covered_keywords.append({
                "keyword": kw,
                "match_type": "exact_or_title" if is_exact else "high_overlap",
                "coverage_score": 1.0 if is_exact else round(token_overlap, 2)
            })
        else:
            # Score missing keyword relevance based on token match with product category or title
            category_tokens = tokenize_text(product.category or "")
            product_title_tokens = tokenize_text(product.product_name)

            cat_overlap = len(kw_tokens.intersection(category_tokens))
            title_overlap = len(kw_tokens.intersection(product_title_tokens))

            # Relevance score computation
            relevance = 1.0 if (cat_overlap > 0 or title_overlap > 0) else 0.6

            missing_keywords.append({
                "keyword": kw,
                "relevance_score": relevance,
                "category_aligned": cat_overlap > 0,
                "title_word_shared": title_overlap > 0
            })

    # Sort missing keywords by relevance score descending
    missing_keywords.sort(key=lambda x: (x["relevance_score"], x["category_aligned"]), reverse=True)

    return {
        "source_product_asin": product.asin,
        "product_name": product.product_name,
        "category": product.category,
        "own_keywords_count": len(own_keywords),
        "own_keywords_sample": own_keywords[:10],
        "competitors_analyzed_count": len(competitor_prods),
        "competitor_sample_titles": [cp.competitor_title for cp in competitor_prods[:5] if cp.competitor_title],
        "total_competitor_keywords_analyzed": len(raw_comp_keywords),
        "filtered_relevant_competitor_keywords_count": len(filtered_comp_keywords),
        "covered_keywords_count": len(covered_keywords),
        "covered_keywords": covered_keywords,
        "missing_keywords_count": len(missing_keywords),
        "missing_keywords": missing_keywords
    }


def run_comparison_for_all_processed(db: Session, limit: int = 10) -> List[Dict[str, Any]]:
    """Run comparison for up to limit processed source products in MySQL."""
    source_asins = [
        r[0] for r in db.query(CompetitorProduct.source_product_asin).distinct().all()
    ][:limit]

    results = []
    for asin in source_asins:
        res = compare_product_against_competitors(db, asin)
        results.append(res)
    return results
