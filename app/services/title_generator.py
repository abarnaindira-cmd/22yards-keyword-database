import logging
import time
from datetime import datetime, timezone
from collections import Counter
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.keyword import Keyword
from app.models.competitor import CompetitorProduct
from app.models.final_product_data import FinalProductData
from app.services.groq_service import get_groq_client

logger = logging.getLogger("title_generator")

MAX_RATE_LIMIT_RETRIES_PER_SKU = 2
MAX_GROQ_REQUESTS_PER_SKU = 6
RATE_LIMIT_BACKOFF_BASE_SECONDS = 2.0


def _http_status_from_error(error: Exception) -> Optional[int]:
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _is_http_429(error: Exception) -> bool:
    return _http_status_from_error(error) == 429 or type(error).__name__ == "RateLimitError"


def _retry_after_seconds(error: Exception, retry_number: int) -> float:
    """Use Retry-After when supplied; otherwise use bounded exponential backoff."""
    fallback = RATE_LIMIT_BACKOFF_BASE_SECONDS * (2 ** max(0, retry_number - 1))
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}
    retry_after_ms = headers.get("retry-after-ms") or headers.get("Retry-After-Ms")
    if retry_after_ms is not None:
        try:
            return max(fallback, float(retry_after_ms) / 1000.0)
        except (TypeError, ValueError):
            pass

    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after is not None:
        try:
            return max(fallback, float(retry_after))
        except (TypeError, ValueError):
            try:
                retry_at = parsedate_to_datetime(str(retry_after))
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(fallback, (retry_at - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    return fallback


def _create_completion_with_rate_limit_retry(
    client: Any,
    request_kwargs: Dict[str, Any],
    sku_id: Optional[str],
    product_name: str,
    diagnostics: Dict[str, Any],
):
    """Make one Groq request, retrying only 429s within the per-SKU budget."""
    while True:
        if diagnostics["request_count"] >= MAX_GROQ_REQUESTS_PER_SKU:
            diagnostics["failure_reason"] = "retry_exhausted"
            logger.warning(
                "GROQ_RETRY_BUDGET SKU=%s Attempt=%d Reason=retry_exhausted "
                "Retry=%d/%d Final result=MANUAL_REVIEW_REQUIRED",
                sku_id or "(direct-call)", diagnostics["request_count"],
                diagnostics["rate_limit_retry_count"], MAX_RATE_LIMIT_RETRIES_PER_SKU,
            )
            return None, "retry_exhausted"

        diagnostics["request_count"] += 1
        attempt_number = diagnostics["request_count"]
        try:
            return client.chat.completions.create(**request_kwargs), None
        except Exception as error:
            status = _http_status_from_error(error)
            if not _is_http_429(error):
                diagnostics["failure_reason"] = "groq_api_error"
                logger.warning(
                    "GROQ_REQUEST_FAILURE SKU=%s Attempt=%d HTTP status=%s Reason=groq_api_error "
                    "Final result=next_model Error=%s",
                    sku_id or "(direct-call)", attempt_number, status or "unknown", type(error).__name__,
                )
                return None, "groq_api_error"

            retry_number = diagnostics["rate_limit_retry_count"] + 1
            if retry_number > MAX_RATE_LIMIT_RETRIES_PER_SKU:
                diagnostics["failure_reason"] = "rate_limit"
                diagnostics["rate_limit_retries_exhausted"] = True
                logger.warning(
                    "429_RATE_LIMIT SKU=%s Attempt=%d HTTP status=429 Reason=rate_limit "
                    "Wait=0 seconds Retry=%d/%d Final result=retry_exhausted",
                    sku_id or "(direct-call)", attempt_number,
                    MAX_RATE_LIMIT_RETRIES_PER_SKU, MAX_RATE_LIMIT_RETRIES_PER_SKU,
                )
                return None, "rate_limit"

            wait_seconds = _retry_after_seconds(error, retry_number)
            diagnostics["rate_limit_retry_count"] = retry_number
            diagnostics["retry_count"] += 1
            diagnostics["failure_reason"] = "rate_limit"
            logger.warning(
                "429_RATE_LIMIT SKU=%s Attempt=%d HTTP status=429 Reason=rate_limit "
                "Wait=%.2f seconds Retry=%d/%d Final result=retrying",
                sku_id or "(direct-call)", attempt_number, wait_seconds,
                retry_number, MAX_RATE_LIMIT_RETRIES_PER_SKU,
            )
            time.sleep(wait_seconds)

import re

def clean_input_text(text: str) -> str:
    if not text:
        return ""
    text = (text.replace('\u2011', '-')
                .replace('\u2010', '-')
                .replace('\u2013', '-')
                .replace('\u2014', '-')
                .replace('\u2018', "'")
                .replace('\u2019', "'")
                .replace('\u201c', '"')
                .replace('\u201d', '"'))
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    return text.strip()

def clean_generated_title(title: str) -> str:
    if not title:
        return ""
    title = clean_input_text(title)
    if title.startswith('"') and title.endswith('"'):
        title = title[1:-1].strip()
    return title

def normalize_title_for_comparison(title: Optional[str]) -> str:
    """Normalize spacing and case for exact-title collision checks."""
    return re.sub(r'\s+', ' ', title or '').strip().casefold()

def normalize_generated_title(title: Optional[str]) -> str:
    """Normalize punctuation, spacing, and case when checking for a genuinely new title."""
    return " ".join(re.findall(r'[a-z0-9]+', clean_input_text(title or '').casefold()))

def validate_generated_title(
    title: Optional[str],
    product_name: str,
    competitor_titles: List[str],
    category: Optional[str] = None,
):
    """Return (accepted, reason) for a title grounded in target facts."""
    candidate = clean_generated_title(title or "")
    normalized = normalize_generated_title(title)
    target = normalize_generated_title(product_name)
    if not candidate or normalized == normalize_generated_title("MANUAL_REVIEW_REQUIRED"):
        return False, "invalid_groq_response"
    if candidate.strip() == clean_input_text(product_name).strip():
        return False, "exact_original_name"
    if normalized and normalized == target:
        return False, "same_after_normalization"

    generated_tokens = normalized.split()
    product_tokens = target.split()
    if not product_tokens:
        return False, "invalid_target_product_name"

    generated_counts = Counter(generated_tokens)
    product_counts = Counter(product_tokens)

    # Do not allow a competitor copy to pass just because it also retains the
    # target's words. Competitor titles remain reference material only.
    for competitor_title in competitor_titles:
        competitor = normalize_generated_title(competitor_title)
        if competitor and (normalized == competitor or SequenceMatcher(None, normalized, competitor).ratio() >= 0.88):
            return False, "competitor_title_copy"

    # Preserve the target's product type and every identity token.
    product_type_phrase = " ".join(product_tokens[-2:])
    if product_type_phrase not in " ".join(generated_tokens):
        return False, "changed_product_type"
    if product_counts - generated_counts:
        return False, "changed_product_identity"

    structural_words = {"a", "an", "and", "by", "for", "in", "of", "the", "with"}
    category_counts = Counter(normalize_generated_title(category).split())
    added_words = generated_counts - product_counts
    if not added_words:
        if generated_tokens != product_tokens:
            return False, "trivial_rearrangement"
        return False, "same_after_normalization"

    # A repeated target-name term, trivial filler, or broad department label
    # does not make a title meaningfully better.
    if added_words & product_counts:
        return False, "trivial_change"
    if any(word in {"new", "single", "best", "premium", "professional"} for word in added_words):
        return False, "trivial_change"
    # Reject an abbreviation/category alias that repeats an already explicit
    # product type (e.g. adding "TT Bat" to "Table Tennis Racquet").
    if (
        {"table", "tennis"}.issubset(product_counts)
        and ({"racquet", "racket"} & set(product_counts))
        and {"tt", "bat"}.issubset(added_words)
    ):
        return False, "trivial_change"

    unsupported_words = added_words - category_counts - Counter(structural_words)
    if unsupported_words:
        return False, "unsupported_wording"

    # A broad category label does not substantiate a use case or a product
    # claim. These terms must be present in the target name itself.
    target_unsupported_claim_terms = {
        "training", "practice", "competition", "waterproof", "silicone",
        "premium", "professional", "best", "durable", "lightweight",
        "adjustable", "anti", "fog", "uv", "protection",
    }
    if added_words & Counter({word: 1 for word in target_unsupported_claim_terms}):
        return False, "unsupported_wording"

    if added_words & Counter({"accessory": 1, "accessories": 1, "apparel": 1, "equipment": 1, "gear": 1, "sportswear": 1, "fitness": 1}):
        return False, "trivial_change"

    if not (added_words - Counter(structural_words)):
        return False, "trivial_change"

    return True, None


def is_valid_generated_title(
    title: Optional[str],
    product_name: str,
    competitor_titles: List[str],
    category: Optional[str] = None,
    allow_case_formatting: bool = False,
) -> bool:
    """Backward-compatible boolean wrapper around reasoned validation."""
    is_valid, _reason = validate_generated_title(title, product_name, competitor_titles, category)
    return is_valid


def _log_title_event(
    sku_id: Optional[str],
    product_name: str,
    generated_title: Optional[str],
    validation_result: str,
    rejection_reason: Optional[str],
    attempt_number: int,
    retry_count: int,
    final_status: str,
) -> None:
    logger.info(
        "TITLE_CANDIDATE sku=%r original=%r generated=%r validation=%s "
        "rejection_reason=%s attempt=%d retry_count=%d final_status=%s",
        sku_id or "(direct-call)", product_name, generated_title or "", validation_result,
        rejection_reason or "none", attempt_number, retry_count, final_status,
    )

def generate_title_with_groq(
    product_name: str,
    competitor_titles: List[str],
    duplicate_titles: Optional[List[str]] = None,
    category: Optional[str] = None,
    allow_case_formatting: bool = False,
    sku_id: Optional[str] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Generate an e-commerce product title using Groq LLM API.
    Uses the target product name as the product identity and competitor titles for reference,
    while avoiding unsupported claims or copied competitor titles.
    """
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.setdefault("request_count", 0)
    diagnostics.setdefault("retry_count", 0)
    diagnostics.setdefault("rate_limit_retry_count", 0)
    diagnostics.setdefault("validation_retry_count", 0)
    diagnostics["failure_reason"] = None
    diagnostics["rejection_reason"] = None
    diagnostics["last_candidate"] = None
    diagnostics["last_validation_result"] = None
    diagnostics["last_attempt"] = diagnostics["request_count"]
    client = get_groq_client()
    if not client:
        logger.warning("Groq client initialization returned None (check GROQ_API_KEY).")
        diagnostics["failure_reason"] = "invalid_groq_response"
        _log_title_event(sku_id, product_name, None, "not_run", "invalid_groq_response", 0, 0, "MANUAL_REVIEW_REQUIRED")
        return None

    clean_prod_name = clean_input_text(product_name)
    clean_comps = [clean_input_text(t) for t in competitor_titles[:20] if t]
    clean_duplicates = [clean_input_text(t) for t in (duplicate_titles or []) if t]

    if not clean_comps:
        logger.warning(f"No competitor titles available for product '{clean_prod_name}'.")
        diagnostics["failure_reason"] = "missing_competitor_data"
        _log_title_event(sku_id, product_name, None, "not_run", "missing_competitor_data", 0, 0, "MANUAL_REVIEW_REQUIRED")
        return None

    comp_summary = "\n".join([f"{i+1}. {t}" for i, t in enumerate(clean_comps)])
    duplicate_summary = "\n".join(f"- {title}" for title in clean_duplicates) or "(none)"

    prompt = f"""You are an expert e-commerce SEO copywriter. Generate ONE impressive, original, search-optimized final product title for Amazon/e-commerce.

Target Product Name: {clean_prod_name}

Target Product Category: {clean_input_text(category or "") or "(not provided)"}

Reference Competitor Product Titles (for phrasing, structure, and search term inspiration ONLY):
{comp_summary}

Existing Titles Used Only to Avoid Exact Duplication:
{duplicate_summary}

AMAZON-READY TITLE QUALITY: Generate a clear, professional Amazon listing title with natural title structure and composition informed by the competitor examples. Create a meaningful improvement, not just the original name with trivial additions such as “Single Color” or “New,” synonym stuffing, or superficial word substitutions. Competitor titles are references for structure and wording patterns only; do not copy or closely paraphrase them. Use only facts present in the Target Product Name or Target Product Category. The category may clarify product class only; it does not verify materials, sizes, audience, fit, benefits, uses, or performance. If these target facts do not support a meaningful improvement, output exactly MANUAL_REVIEW_REQUIRED.

STRICT TRANSFER RULE: Do not transfer competitor-specific features, benefits, materials, sizes, audiences, use cases, performance claims, or product types to the target. Never change the target product type. Do not add subjective claims such as “Premium,” “Professional,” or “Best,” or use cases such as “Training,” “Open Water,” or “Competition,” unless explicitly supported by the Target Product Name or Target Product Category. Preserve the target’s wording and identity; do not unnecessarily pluralize, reclassify, or otherwise alter it.

STRICT PRODUCT TRUTH RULES:
1. PRESERVE IDENTITY: The title MUST retain every important distinguishing detail present in the Target Product Name, including brand, model/SKU identifiers, size, material, product type, and other meaningful identifiers. Do not replace these with generic wording or omit them for brevity.
2. VERIFIED ATTRIBUTES ONLY: A competitor title is never evidence that the target has an attribute. Include a feature, benefit, material, size, audience, use case, or performance claim only when explicitly supported by the Target Product Name. The Target Product Category may clarify product class only.
4. DISTINCT OUTPUT: Do not produce any title identical to one in Existing Titles Used Only to Avoid Exact Duplication. Preserve the target's distinguishing details so this product remains identifiable.
5. CONCISE & CLEAN: Output ONLY the raw final product title (under 200 characters) without quotes, markdown headers, or preamble.
"""

    models_to_try = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
    for model_name in models_to_try:
        request_kwargs = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You generate concise, compliant e-commerce product titles."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 1000,
        }
        completion, request_error = _create_completion_with_rate_limit_retry(
            client, request_kwargs, sku_id, product_name, diagnostics,
        )
        if request_error == "rate_limit":
            diagnostics["failure_reason"] = "rate_limit"
            _log_title_event(sku_id, product_name, None, "not_run", "rate_limit", diagnostics["request_count"], diagnostics["retry_count"], "MANUAL_REVIEW_REQUIRED")
            return None
        if request_error == "retry_exhausted":
            diagnostics["failure_reason"] = "retry_exhausted"
            _log_title_event(sku_id, product_name, None, "not_run", "retry_exhausted", diagnostics["request_count"], diagnostics["retry_count"], "MANUAL_REVIEW_REQUIRED")
            return None
        if request_error:
            diagnostics["failure_reason"] = request_error
            continue

        raw_content = completion.choices[0].message.content or ""
        cleaned = clean_generated_title(raw_content)
        if not cleaned:
            diagnostics["failure_reason"] = "invalid_groq_response"
            diagnostics["last_candidate"] = ""
            diagnostics["last_validation_result"] = "rejected"
            diagnostics["last_attempt"] = diagnostics["request_count"]
            _log_title_event(
                sku_id, product_name, "", "rejected", "invalid_groq_response",
                diagnostics["request_count"], diagnostics["retry_count"], "next_model",
            )
            continue

        valid, rejection_reason = validate_generated_title(cleaned, product_name, clean_comps, category)
        diagnostics["last_candidate"] = cleaned
        diagnostics["last_validation_result"] = "accepted" if valid else "rejected"
        diagnostics["last_attempt"] = diagnostics["request_count"]
        _log_title_event(
            sku_id, product_name, cleaned, "accepted" if valid else "rejected",
            rejection_reason, diagnostics["request_count"], diagnostics["retry_count"],
            "accepted" if valid else "targeted_retry",
        )
        if valid:
            diagnostics["failure_reason"] = None
            logger.info("Successfully generated title using Groq model '%s'", model_name)
            return cleaned

        diagnostics["rejection_reason"] = rejection_reason
        diagnostics["failure_reason"] = "title_validation_failure"
        retry_prompt = prompt + f"""

TARGETED RETRY: The previous candidate was rejected for: {rejection_reason}. Produce a genuinely useful, professional title that differs meaningfully from the Target Product Name. Preserve its complete identity and product type. Competitor titles are references for structure only. Add no unsupported facts. If no safe improvement is possible, output exactly MANUAL_REVIEW_REQUIRED.
"""
        retry_kwargs = dict(request_kwargs)
        retry_kwargs["messages"] = [
            {"role": "system", "content": "You generate concise, compliant e-commerce product titles."},
            {"role": "user", "content": retry_prompt},
        ]
        diagnostics["validation_retry_count"] += 1
        diagnostics["retry_count"] += 1
        retry_completion, retry_error = _create_completion_with_rate_limit_retry(
            client, retry_kwargs, sku_id, product_name, diagnostics,
        )
        if retry_error:
            diagnostics["failure_reason"] = "rate_limit" if retry_error == "rate_limit" else retry_error
            _log_title_event(
                sku_id, product_name, None, "not_run", diagnostics["failure_reason"],
                diagnostics["request_count"], diagnostics["retry_count"], "MANUAL_REVIEW_REQUIRED",
            )
            return None

        retry_raw = retry_completion.choices[0].message.content or ""
        retry_title = clean_generated_title(retry_raw)
        if not retry_title:
            retry_valid, retry_rejection = False, "invalid_groq_response"
        else:
            retry_valid, retry_rejection = validate_generated_title(retry_title, product_name, clean_comps, category)
        diagnostics["last_candidate"] = retry_title
        diagnostics["last_validation_result"] = "accepted" if retry_valid else "rejected"
        diagnostics["last_attempt"] = diagnostics["request_count"]
        _log_title_event(
            sku_id, product_name, retry_title, "accepted" if retry_valid else "rejected",
            retry_rejection, diagnostics["request_count"], diagnostics["retry_count"],
            "accepted" if retry_valid else "retry_exhausted",
        )
        if retry_valid:
            diagnostics["failure_reason"] = None
            diagnostics["rejection_reason"] = None
            logger.info("Successfully generated title using targeted retry with model '%s'", model_name)
            return retry_title

        diagnostics["rejection_reason"] = retry_rejection
        diagnostics["failure_reason"] = "invalid_groq_response" if retry_rejection == "invalid_groq_response" else "retry_exhausted"
        logger.warning("Targeted title retry failed validation for product '%s'.", clean_prod_name)
        return None

    if diagnostics.get("failure_reason") not in {"invalid_groq_response", "groq_api_error"}:
        diagnostics["failure_reason"] = "retry_exhausted"
    _log_title_event(
        sku_id, product_name, None, "not_accepted", diagnostics.get("failure_reason"),
        diagnostics.get("request_count", 0), diagnostics.get("retry_count", 0), "MANUAL_REVIEW_REQUIRED",
    )
    return None

def process_final_product_data_for_asin(db: Session, sku_id: str) -> Dict[str, Any]:
    """
    Process single product by sku_id (ASIN):
    1. Read product and keywords from DB.
    2. Read competitor titles from DB.
    3. Generate final product title using Groq (or mark MANUAL_REVIEW_REQUIRED if API unconfigured/fails/no competitors).
    4. Store all keywords in a JSON array in final_product_data table.
    5. Avoid duplicates via safe upsert.
    """
    prod = db.query(Product).filter(Product.asin == sku_id).first()
    if not prod:
        return {"error": f"Product with SKU/ASIN {sku_id} not found."}

    # Completed titles are immutable in this processing path. Only rows already
    # marked for manual review are eligible for this conservative recovery.
    existing = db.query(FinalProductData).filter(FinalProductData.sku_id == sku_id).first()
    if existing and normalize_title_for_comparison(existing.final_product_title) != normalize_title_for_comparison("MANUAL_REVIEW_REQUIRED"):
        saved_keywords = existing.all_keywords or []
        return {
            "sku_id": sku_id,
            "product_name": existing.product_name or prod.product_name,
            "final_product_title": existing.final_product_title,
            "keywords_count": len(saved_keywords),
            "all_keywords": saved_keywords,
            "generation_method": "existing",
        }

    # Fetch keywords
    kw_rows = db.query(Keyword).filter(
        Keyword.source_product_asin == sku_id
    ).order_by(Keyword.relevance_score.desc()).all()

    all_keywords_list = [k.keyword for k in kw_rows if k.keyword]

    # Fetch up to 20 competitor titles, preferring the best recorded rank.
    comp_rows = db.query(CompetitorProduct).filter(
        CompetitorProduct.source_product_asin == sku_id
    ).order_by(CompetitorProduct.competitor_rank.asc()).all()

    comp_titles_raw = [c.competitor_title for c in comp_rows if c.competitor_title and c.competitor_title.strip()]
    competitor_titles = []
    for t in comp_titles_raw:
        t_clean = t.strip()
        if t_clean not in competitor_titles:
            competitor_titles.append(t_clean)
        if len(competitor_titles) >= 20:
            break

    # Avoid exact title collisions with other SKUs already stored in final_product_data.
    other_titles = [
        title for title, other_sku in db.query(
            FinalProductData.final_product_title, FinalProductData.sku_id
        ).filter(FinalProductData.sku_id != sku_id).all()
        if title and normalize_title_for_comparison(title) != normalize_title_for_comparison("MANUAL_REVIEW_REQUIRED")
    ]
    normalized_existing_titles = {normalize_title_for_comparison(title) for title in other_titles}

    # Existing manual-review rows are retried only when their product name is
    # unique. Duplicate names without a verified variant remain ambiguous.
    manual_recovery = bool(existing)
    generation_diagnostics: Dict[str, Any] = {}
    generation_status_reason: Optional[str] = None
    if manual_recovery:
        duplicate_product_names = db.query(Product).filter(
            func.lower(func.trim(Product.product_name)) == prod.product_name.strip().casefold()
        ).count()
        if duplicate_product_names > 1:
            generation_status_reason = "duplicate_name_ambiguity"
            _log_title_event(sku_id, prod.product_name, None, "not_run", "duplicate_name_ambiguity", 0, 0, "MANUAL_REVIEW_REQUIRED")
            final_title = None
        else:
            final_title = generate_title_with_groq(
                prod.product_name,
                competitor_titles,
                category=getattr(prod, "category", None),
                allow_case_formatting=True,
                sku_id=sku_id,
                diagnostics=generation_diagnostics,
            )
    else:
        final_title = generate_title_with_groq(prod.product_name, competitor_titles, sku_id=sku_id, diagnostics=generation_diagnostics)

    # Generate Title using Groq or mark MANUAL_REVIEW_REQUIRED.
    method = "groq"
    if final_title and normalize_title_for_comparison(final_title) in normalized_existing_titles:
        _log_title_event(sku_id, prod.product_name, final_title, "rejected", "duplicate_generated_title", 1, 0, "targeted_retry")
        if manual_recovery:
            final_title = generate_title_with_groq(
                prod.product_name,
                competitor_titles,
                duplicate_titles=other_titles,
                category=getattr(prod, "category", None),
                allow_case_formatting=True,
                sku_id=sku_id,
                diagnostics=generation_diagnostics,
            )
        else:
            final_title = generate_title_with_groq(
                prod.product_name,
                competitor_titles,
                duplicate_titles=other_titles,
                sku_id=sku_id,
                diagnostics=generation_diagnostics,
            )
        if final_title and normalize_title_for_comparison(final_title) in normalized_existing_titles:
            _log_title_event(sku_id, prod.product_name, final_title, "rejected", "duplicate_generated_title", 2, 1, "MANUAL_REVIEW_REQUIRED")
            final_title = None

    if not final_title:
        method = "manual_review"
        final_title = "MANUAL_REVIEW_REQUIRED"
        status_reason = generation_diagnostics.get("failure_reason") or generation_status_reason or "title_validation_failure"
        generation_status_reason = status_reason
        _log_title_event(sku_id, prod.product_name, None, "not_accepted", status_reason, generation_diagnostics.get("request_count", 0), generation_diagnostics.get("retry_count", 0), "MANUAL_REVIEW_REQUIRED")

    # Upsert into final_product_data
    if existing:
        existing.product_name = prod.product_name
        existing.final_product_title = final_title
        existing.all_keywords = all_keywords_list
    else:
        new_entry = FinalProductData(
            product_name=prod.product_name,
            sku_id=sku_id,
            final_product_title=final_title,
            all_keywords=all_keywords_list
        )
        db.add(new_entry)

    db.commit()

    return {
        "sku_id": sku_id,
        "product_name": prod.product_name,
        "final_product_title": final_title,
        "keywords_count": len(all_keywords_list),
        "all_keywords": all_keywords_list,
        "generation_method": method,
        "generation_status_reason": generation_status_reason or generation_diagnostics.get("failure_reason"),
    }

def process_batch_final_product_data(db: Session, target_asins: List[str]) -> Dict[str, Any]:
    """
    Process ONLY the products matching target_asins list.
    Returns metrics: total_uploaded, groq_generated_count, manual_review_count, failed_count.
    """
    prods = db.query(Product).filter(Product.asin.in_(target_asins)).order_by(Product.id.asc()).all()
    results = []
    groq_count = 0
    manual_review_count = 0
    failed_count = 0

    for p in prods:
        res = process_final_product_data_for_asin(db, p.asin)
        if "error" in res:
            failed_count += 1
        else:
            if res.get("generation_method") == "groq":
                groq_count += 1
            else:
                manual_review_count += 1
            results.append(res)
        time.sleep(1.0)

    return {
        "total_uploaded": len(target_asins),
        "total_processed": len(prods),
        "groq_generated_count": groq_count,
        "manual_review_count": manual_review_count,
        "failed_count": failed_count,
        "details": results
    }

def process_all_final_product_data(db: Session, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Process all or limited products in products table and generate final_product_data records.
    """
    query = db.query(Product).order_by(Product.id.asc())
    if limit:
        query = query.limit(limit)

    prods = query.all()
    results = []
    groq_count = 0
    manual_review_count = 0
    failed_count = 0

    for p in prods:
        res = process_final_product_data_for_asin(db, p.asin)
        if "error" in res:
            failed_count += 1
        else:
            if res.get("generation_method") == "groq":
                groq_count += 1
            else:
                manual_review_count += 1
            results.append(res)

    return {
        "total_processed": len(prods),
        "groq_generated_count": groq_count,
        "manual_review_count": manual_review_count,
        "failed_count": failed_count,
        "details": results
    }
