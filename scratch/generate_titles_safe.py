"""
Safe controlled title generator (22yards).

Our product name + existing competitor Amazon titles (competitor_products)
  -> Groq -> NEW title -> validate -> save ONLY valid titles.
Invalid / failed SKUs are left untouched (stay MANUAL_REVIEW_REQUIRED).

Place this file in:  22yards_keyword_database\\scratch\\
Run from project root (22yards_keyword_database):

  1) Dry run (NO Groq call, NO DB write) - see what would be processed:
     python scratch/generate_titles_safe.py --skus-file skus_100.txt --dry-run

  2) Small live test, results only to CSV (NO DB write):
     python scratch/generate_titles_safe.py --skus-file skus_100.txt --limit 3

  3) Same, but save valid titles to final_product_data:
     python scratch/generate_titles_safe.py --skus-file skus_100.txt --limit 3 --commit

skus_100.txt = one SKU per line (commas also fine).

Rules implemented:
  * all_keywords is never read for the prompt and never modified.
  * Guard: only a REAL title counts as completed. Empty, MANUAL_REVIEW_REQUIRED,
    a title containing '|', or a title equal to the product name = pending.
  * Groq SDK retries disabled (max_retries=0). We retry only HTTP 429, at most
    2 times per SKU, honouring Retry-After-Ms / Retry-After, else exponential.
  * If the required wait is longer than --max-wait seconds (long cooldown),
    the whole run stops cleanly; remaining SKUs are left untouched.
  * --limit caps the number of Groq generation calls in the run.
"""
import argparse
import csv
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MANUAL = "MANUAL_REVIEW_REQUIRED"
MODEL_DEFAULT = "openai/gpt-oss-120b"


# ---------------------------------------------------------------- pure helpers
def clean_text(text):
    if not text:
        return ""
    text = (text.replace("\u2011", "-").replace("\u2010", "-")
                .replace("\u2013", "-").replace("\u2014", "-")
                .replace("\u2018", "'").replace("\u2019", "'")
                .replace("\u201c", '"').replace("\u201d", '"'))
    return re.sub(r"[^\x00-\x7F]+", " ", text).strip()


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").casefold()).strip()


def is_real_title(title, product_name):
    """True only if title is an actual generated title (= task completed)."""
    if not title or not title.strip():
        return False
    t = title.strip()
    if t == MANUAL or "|" in t:
        return False
    if product_name and norm(t) == norm(product_name):
        return False
    return True


FACT_COLS = [
    ("Brand", "Brand Name"),
    ("Product category", "Product Category"),
    ("Product description (internal)", "Product Description on Invoice"),
    ("Colour", "Colour"),
    ("Size", "Size"),
]
EMPTY = {"", "NA", "N/A", "NAN", "NONE", "-"}


def load_master(path):
    """sku -> list of (label, value) VERIFIED facts from our own master Excel."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    idx = {h: i for i, h in enumerate(header)}
    sku_i = idx["SKU ID for Market Places"]
    out = {}
    for r in rows:
        sku = str(r[sku_i]).strip() if r[sku_i] is not None else ""
        if not sku or sku in out:
            continue
        facts = []
        for label, col in FACT_COLS:
            if col not in idx:
                continue
            v = r[idx[col]]
            v = clean_text(str(v)) if v is not None else ""
            if v.strip().upper() in EMPTY:
                continue
            facts.append((label, " ".join(v.split())))
        out[sku] = facts
    wb.close()
    return out


STATS = {"requests": 0}

# Words that make a claim / audience / use-case. Allowed ONLY if they already
# appear in the product name or our verified facts.
CLAIM_WORDS = {
    "perfect", "ideal", "suitable", "best", "premium", "quality", "durable", "durability",
    "ultimate", "superior", "advanced", "professional", "recreational", "beginner", "beginners",
    "comfortable", "comfort", "lightweight", "waterproof", "anti", "fog", "uv", "protection",
    "resistant", "leakproof", "ergonomic", "performance", "kids", "kid", "children", "boys",
    "girls", "women", "ladies", "adult", "adults", "unisex", "junior", "senior",
}


def validate_title(title, product_name, competitor_titles, source_text=""):
    """Return (ok, reason). source_text = product name + verified facts."""
    t = (title or "").strip()
    if not t:
        return False, "empty"
    if "\n" in t or "|" in t or "**" in t or "#" in t:
        return False, "format_not_clean"
    if len(t) > 200:
        return False, "too_long"
    if t == MANUAL:
        return False, "is_marker"
    if norm(t) == norm(product_name):
        return False, "same_as_product_name"
    if any(norm(t) == norm(c) for c in competitor_titles):
        return False, "copied_competitor_title"
    if re.search(r"\b(\w+)\s+\1\b", t, flags=re.I):
        return False, "repeated_words"
    allowed_nums = set(re.findall(r"\d+(?:\.\d+)?", source_text or product_name))
    if not set(re.findall(r"\d+(?:\.\d+)?", t)) <= allowed_nums:
        return False, "invented_number"
    src_tokens = set(norm(source_text or product_name).split())
    for w in norm(t).split():
        if w in CLAIM_WORDS and w not in src_tokens:
            return False, f"unverified_claim:{w}"
    brand = norm(product_name).split(" ")[0] if norm(product_name) else ""
    if brand and brand not in norm(t):
        return False, "brand_token_missing"
    return True, "ok"


def build_prompt(product_name, competitor_titles, facts):
    comps = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(competitor_titles))
    fact_lines = "\n".join(f"- {k}: {v}" for k, v in facts) or "- (none available)"
    return f"""You are an expert Amazon India listing copywriter. Write ONE professional, readable Amazon product title for OUR product.

Our Product Name (source of truth for identity): {product_name}

Verified facts about OUR product (from our own master data, safe to use):
{fact_lines}

Competitor Amazon titles (learn ONLY structure, ordering, level of detail and style):
{comps}

RULES:
1. Facts about OUR product may come ONLY from the Our Product Name and the Verified facts above.
2. Write a rich, professional Amazon-style title of about 80-150 characters: Brand + Model/Series + Product Type + key verified attributes (colour, size, gender only if verified) + natural search terms.
3. SEARCH TERMS: you may add words that say WHAT the product is and how it is used (product type, sport, usage, e.g. "Swimming Goggles", "for Swimming", "Table Tennis Ball") when they appear in several competitor titles. These describe the product type, they are not specifications.
4. The title must be meaningfully different from the Our Product Name (better structure and wording) while keeping the same brand, model and product type.
5. Do NOT invent or assume any specification, feature or claim: size, material, quantity, age group, audience, anti-fog, UV protection, waterproof, durability, benefits, performance, certification. Competitor specs and claims are never facts about our product. No marketing phrases such as "perfect for", "ideal for", "best", "premium", "high quality" and no use-case sentences.
6. Do NOT copy any competitor title and do NOT use any competitor brand name.
7. No repeated words, no keyword stuffing, no all-caps shouting.
8. If a safe meaningful title is not possible, output exactly: {MANUAL}
9. Output ONLY the title text (under 200 characters). No quotes, markdown or explanation.
"""


def retry_wait_seconds(exc, attempt):
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        ms = headers.get("retry-after-ms")
        if ms:
            return float(ms) / 1000.0
        ra = headers.get("retry-after")
        if ra:
            return float(ra)
    except (ValueError, TypeError):
        pass
    return float(5 * (2 ** attempt))  # 5s, 10s


# ------------------------------------------------------------------- Groq call
def call_groq(client, model, prompt, max_429_retries, max_wait, max_tokens=1500):
    """Return (text, error). error starting with 'COOLDOWN' means stop the whole run."""
    attempt = 0
    bumped = False
    while True:
        try:
            STATS["requests"] += 1
            r = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You write concise, truthful e-commerce product titles."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=max_tokens,
            )
            ch = r.choices[0]
            text = ch.message.content or ""
            if not text.strip() and getattr(ch, "finish_reason", "") == "length" and not bumped:
                bumped = True
                max_tokens *= 3
                print("      empty answer (token limit) -> one retry with a larger limit", flush=True)
                continue
            return text, None
        except Exception as e:  # noqa: BLE001
            status = getattr(e, "status_code", None)
            if status == 429:
                wait = retry_wait_seconds(e, attempt)
                if wait > max_wait:
                    return None, f"COOLDOWN (needs {wait:.0f}s)"
                if attempt < max_429_retries:
                    attempt += 1
                    print(f"      429 -> waiting {wait:.0f}s (retry {attempt}/{max_429_retries})", flush=True)
                    time.sleep(wait)
                    continue
                return None, "RATE_LIMIT_RETRIES_EXHAUSTED"
            return None, type(e).__name__


def generate_one(client, args, product_name, comps, facts, source_text):
    """Up to 2 attempts (1 repair). Returns (status, title, reason)."""
    base = build_prompt(clean_text(product_name), comps, facts)
    prompt, title, reason = base, "", ""
    for attempt in (1, 2):
        text, err = call_groq(client, args.model, prompt, args.retries_429, args.max_wait)
        if err:
            return ("COOLDOWN_STOPPED" if err.startswith("COOLDOWN") else "GROQ_ERROR"), "", err
        title = clean_text(text).strip('"').strip()
        ok, reason = validate_title(title, product_name, comps, source_text)
        if ok:
            return "VALID", title, ("ok" if attempt == 1 else "ok_after_repair")
        if reason == "is_marker" or attempt == 2:
            break
        print(f"      rejected ({reason}) -> one repair attempt", flush=True)
        time.sleep(args.delay)
        prompt = (base + f"\nYour previous answer was REJECTED because: {reason}.\n"
                  f"Previous answer: {title or '(empty)'}\n"
                  "Rewrite the title and fix exactly that problem. Remove any word or claim that is not "
                  "supported by the Our Product Name or the Verified facts. Output ONLY the title.\n")
    return "INVALID", title, reason


def load_skus(args):
    raw = []
    if args.skus:
        raw += re.split(r"[,\s]+", args.skus)
    if args.skus_file:
        with open(args.skus_file, encoding="utf-8") as f:
            raw += re.split(r"[,\s]+", f.read())
    seen, out = set(), []
    for s in raw:
        s = s.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skus", help="comma separated SKUs")
    ap.add_argument("--skus-file", help="text file, one SKU per line")
    ap.add_argument("--limit", type=int, default=3, help="max SKUs sent to Groq this run (each SKU = 1 call, +1 repair at most)")
    ap.add_argument("--dry-run", action="store_true", help="no Groq calls, no DB writes")
    ap.add_argument("--commit", action="store_true", help="write VALID titles to final_product_data")
    ap.add_argument("--force", action="store_true", help="also regenerate SKUs that already have a real title")
    ap.add_argument("--master", default="22Y_SKU_Master_Updated.xlsx",
                    help="our master Excel (verified Brand/Category/Colour/Size)")
    ap.add_argument("--model", default=MODEL_DEFAULT)
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between Groq calls")
    ap.add_argument("--max-wait", type=float, default=90.0, help="stop run if a 429 wait exceeds this")
    ap.add_argument("--retries-429", type=int, default=2)
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    skus = load_skus(args)
    if not skus:
        print("No SKUs given. Use --skus or --skus-file.")
        return

    master = {}
    if os.path.exists(args.master):
        master = load_master(args.master)
        print(f"Master Excel loaded: {args.master} ({len(master)} SKUs)")
    else:
        print(f"WARNING: master Excel not found at '{args.master}' - using product name only.")

    from app.database import SessionLocal
    from app.models.product import Product
    from app.models.competitor import CompetitorProduct
    from app.models.final_product_data import FinalProductData

    client = None
    if not args.dry_run:
        from groq import Groq
        from app.config import get_groq_api_key
        key = get_groq_api_key()
        if not key:
            print("GROQ_API_KEY not configured.")
            return
        client = Groq(api_key=key, max_retries=0)  # SDK retries OFF

    db = SessionLocal()
    rows, calls = [], 0
    stopped = False
    print(f"SKUs given: {len(skus)} | limit(SKUs): {args.limit} | dry_run={args.dry_run} | commit={args.commit}\n")

    try:
        for sku in skus:
            prod = db.query(Product).filter(Product.asin == sku).first()
            if not prod:
                rows.append([sku, "", "PRODUCT_NOT_FOUND", "", "", 0])
                print(f"[NOT FOUND ] {sku}")
                continue

            fpd = db.query(FinalProductData).filter(FinalProductData.sku_id == sku).first()
            existing = fpd.final_product_title if fpd else ""
            if is_real_title(existing, prod.product_name) and not args.force:
                rows.append([sku, prod.product_name, "SKIPPED_REAL_TITLE", existing, "", 0])
                print(f"[SKIP real ] {sku}")
                continue

            comps = []
            q = (db.query(CompetitorProduct)
                   .filter(CompetitorProduct.source_product_asin == sku)
                   .order_by(CompetitorProduct.competitor_rank.asc()).all())
            for c in q:
                t = clean_text(c.competitor_title)
                if t and t not in comps:
                    comps.append(t)
                if len(comps) >= 20:
                    break

            if not comps:
                rows.append([sku, prod.product_name, "NO_COMPETITOR_TITLES", "", "", 0])
                print(f"[NO COMPS  ] {sku}")
                continue

            if args.dry_run:
                rows.append([sku, prod.product_name, "WOULD_GENERATE", "", "", len(comps)])
                print(f"[WOULD RUN ] {sku} | competitor titles: {len(comps)} | {prod.product_name}")
                continue

            if calls >= args.limit:
                rows.append([sku, prod.product_name, "NOT_RUN_LIMIT_REACHED", "", "", len(comps)])
                continue

            facts = master.get(sku, [])
            source_text = clean_text(prod.product_name) + " " + " ".join(v for _, v in facts)
            calls += 1
            print(f"[GROQ {calls}/{args.limit}] {sku} | {prod.product_name}", flush=True)
            status, title, reason = generate_one(client, args, prod.product_name, comps, facts, source_text)
            if status in ("COOLDOWN_STOPPED", "GROQ_ERROR"):
                rows.append([sku, prod.product_name, status, "", reason, len(comps)])
                print(f"      {status}: {reason}")
                if status == "COOLDOWN_STOPPED":
                    stopped = True
                    break
                continue
            if status == "VALID":
                rows.append([sku, prod.product_name, "VALID", title, reason, len(comps)])
                print(f"      VALID  -> {title}")
                if args.commit:
                    if fpd:
                        fpd.final_product_title = title  # all_keywords untouched
                    else:
                        db.add(FinalProductData(product_name=prod.product_name, sku_id=sku,
                                                final_product_title=title))
                    db.commit()
            else:
                rows.append([sku, prod.product_name, "INVALID", title, reason, len(comps)])
                print(f"      INVALID ({reason}) -> {title}")
            time.sleep(args.delay)
    finally:
        db.close()

    out = f"title_run_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["sku_id", "product_name", "status", "generated_title", "reason", "competitor_titles"])
        w.writerows(rows)

    counts = {}
    for r in rows:
        counts[r[2]] = counts.get(r[2], 0) + 1
    print("\n" + "=" * 60)
    print("SUMMARY:", counts)
    print(f"SKUs sent to Groq: {calls} | Groq HTTP requests: {STATS['requests']} | DB writes: {'valid titles only' if args.commit else 'NONE'}")
    if stopped:
        print("Run stopped early because of a long Groq cooldown. Remaining SKUs untouched.")
    print(f"CSV saved: {out}")


if __name__ == "__main__":
    main()
