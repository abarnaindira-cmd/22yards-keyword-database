import html
import re
from typing import List, Dict, Any

STOP_WORDS = {
    "a", "an", "the", "and", "or", "for", "with", "in", "on", "at", "to", "from",
    "by", "of", "is", "are", "was", "were", "be", "been", "being", "it", "its",
    "this", "that", "these", "those", "you", "your", "our", "my", "we", "all",
    "any", "can", "has", "have", "had", "not", "but", "very", "also", "just",
    "about", "into", "over", "after", "such", "than", "other", "some", "only",
    "more", "most", "no", "if", "out", "up", "so", "as", "how", "what",
    "when", "where", "who", "which", "why", "brand", "best", "good", "great",
    "product", "quality", "buy", "purchase", "seller", "amazon", "item"
}

PRODUCT_NOUNS = {
    "cap", "caps", "goggle", "goggles", "plug", "plugs", "earplug", "earplugs",
    "noseplug", "noseplugs", "mask", "masks", "bag", "bags", "accessory",
    "accessories", "kit", "kits", "set", "sets", "tube", "tubes", "costume",
    "costumes", "gear", "gears", "swimsuit", "swimming", "swim", "diving",
    "snorkel", "racket", "bat", "ball", "helmet", "shorts", "jacket", "pant",
    "shoes", "pad", "guard", "grip", "trophy", "tshirt", "t-shirt", "shirt"
}

FEATURE_KEYWORDS = {
    "waterproof", "water-proof", "water resistant", "water-resistant", "anti-fog",
    "anti fog", "silicone", "adjustable", "uv", "uv protected", "protective",
    "durable", "skin friendly", "skin-friendly", "memory technology", "ergonomic",
    "non slip", "non-slip", "leak resistant", "leak-resistant", "inflatable",
    "padded", "elastic", "lightweight", "breathable", "quick dry", "scratch resistant",
    "latex free", "scratch resistant", "flexible", "comfortable"
}

FRAGMENT_PREFIXES = {
    "made from", "crafted from", "crafted with", "have super", "glass height",
    "belt size", "ideal for", "eye to", "wear without", "top class", "excellent",
    "with 2", "multicolour", "8 years", "100", "integrating", "softer than",
    "includes a", "providing top", "proof seal", "easy to", "perfect for",
    "designed for", "suitable for", "engineered with", "enhances the",
    "crafted with", "features a", "comes with"
}

TRAILING_JUNK = {
    "from", "with", "and", "or", "for", "in", "on", "at", "by", "of", "is", "are",
    "have", "has", "made", "crafted", "includes", "than", "the", "a", "an",
    "which", "that", "this", "these", "those", "their", "your", "our", "my",
    "providing", "including", "feature", "features", "anti"
}


def is_relevant_keyword(phrase: str) -> bool:
    """
    Quality & relevance filter for competitor keywords:
    - Filters incomplete fragments, sentence fragments, trailing junk, generic marketing fluff.
    - Requires 2-5 words with at least 2 non-stop meaningful words.
    - Must contain a recognized product noun or feature keyword.
    """
    if not phrase or len(phrase.strip()) < 3:
        return False

    p_clean = re.sub(r"[^\w\s]", " ", phrase.lower()).strip()
    p_clean = re.sub(r"\s+", " ", p_clean)
    words = p_clean.split()

    if not (2 <= len(words) <= 5):
        return False

    # Check trailing junk words
    if words[-1] in TRAILING_JUNK or words[0] in TRAILING_JUNK:
        return False

    # Check fragment prefixes
    for prefix in FRAGMENT_PREFIXES:
        if p_clean.startswith(prefix) or prefix in p_clean:
            return False

    # Check pure number/dimension junk
    if re.search(r"^\d+\s*(cm|mm|inch|inches|g|kg|m|ml|l)?$", p_clean):
        return False

    meaningful = [w for w in words if len(w) > 1 and not w.isdigit() and w not in STOP_WORDS]
    if len(meaningful) < 2:
        return False

    # Verify presence of product noun OR feature keyword
    has_noun = any(w in PRODUCT_NOUNS for w in words)
    has_feature = any(f in p_clean for f in FEATURE_KEYWORDS)

    return has_noun or has_feature


def extract_keywords_from_text(text: str, max_keywords: int = 20) -> List[str]:
    """Extract meaningful, relevant 2-5 word keyword phrases from raw product listing text."""
    if not text:
        return []

    t = html.unescape(text)
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"\[.*?\]", " ", t)

    clauses = re.split(r"[,|/\-\\.\n\r\t!?;:]", t)

    extracted_phrases = []
    seen_lower = set()

    for clause in clauses:
        clean = re.sub(r"[^\w\s]", " ", clause)
        clean = re.sub(r"\s+", " ", clean).strip()

        if not clean:
            continue

        words = clean.split()
        if 2 <= len(words) <= 5:
            phrase = " ".join(words).strip()
            phrase_lower = phrase.lower()

            if phrase_lower not in seen_lower and is_relevant_keyword(phrase):
                seen_lower.add(phrase_lower)
                extracted_phrases.append(phrase)

        if len(extracted_phrases) >= max_keywords:
            break

    return extracted_phrases


def extract_competitor_keywords_from_details(
    details_list: List[Dict[str, Any]],
    max_keywords: int = 30,
) -> List[str]:
    """Combine text from title, description, bullet points, and reviews across competitor details and extract unique relevant keywords."""
    combined_phrases: List[str] = []
    seen_lower = set()

    for detail in details_list:
        title = detail.get("title") or ""
        desc = detail.get("description") or ""
        bullets = " ".join(detail.get("bullet_points") or [])
        reviews = " ".join(detail.get("reviews") or [])

        full_text = f"{title}. {bullets}. {desc}. {reviews}"
        phrases = extract_keywords_from_text(full_text, max_keywords=15)

        for p in phrases:
            p_lower = p.lower()
            if p_lower not in seen_lower:
                seen_lower.add(p_lower)
                combined_phrases.append(p)
                if len(combined_phrases) >= max_keywords:
                    return combined_phrases

    return combined_phrases
