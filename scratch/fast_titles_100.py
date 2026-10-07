"""
FAST title generation for a confirmed SKU list (22yards) - standalone, does not
change production code.

  Generate (reads MySQL with SELECT only, calls Groq, NO database write):
      python scratch/fast_titles_100.py
  Re-run after a stop: it resumes and only redoes SKUs that are not finished.
      python scratch/fast_titles_100.py --out-dir scratch/fast_titles_<same folder>
  After you review the CSV, write titles to final_product_data:
      python scratch/fast_titles_100.py --apply scratch/fast_titles_<ts>/titles_review.csv

Output folder scratch/fast_titles_<timestamp>/:
  titles_review.csv          one row per SKU with status, title, reason, flags
  Final_Product_Data_100.xlsx  product_name, sku_id, final_product_title, all_keywords
  progress.json              resume cache

Status values:
  AI_VALID       Groq title that passed validation (+ verified colour/size added)
  TEMPLATE       Groq failed or was unavailable; title built only from verified facts
  KEPT_EXISTING  SKU already had a real title; left unchanged
  MANUAL         cannot be titled safely (reason column says why)

Facts about OUR product come only from the product name and the master Excel
(Brand, Category, Colour, Size, Invoice description, Website name). Competitor
titles are used only for structure and common search terms.

--apply writes ONLY rows with status AI_VALID or TEMPLATE whose "approve" cell
is not "no", and only where the current title is MANUAL_REVIEW_REQUIRED.
all_keywords and product_name are never changed.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL = "MANUAL_REVIEW_REQUIRED"
EMPTY_VALUES = {"", "NA", "N/A", "NAN", "NONE", "NULL", "-"}
DEFAULT_MODELS = "openai/gpt-oss-120b,openai/gpt-oss-20b"
SUSPECT_COLOURS = {"solver/white", "white/greay", "blacl/yellow"}  # known master typos: colour is not used as a fact

# Claim / marketing / use-case / audience words: allowed only if present in OUR facts.
CLAIM_WORDS = {
    "perfect", "ideal", "suitable", "best", "premium", "quality", "high", "durable", "durability",
    "ultimate", "superior", "advanced", "professional", "pro", "recreational", "beginner",
    "beginners", "comfortable", "comfort", "lightweight", "light", "waterproof", "anti", "fog", "uv",
    "protection", "protective", "resistant", "leakproof", "ergonomic", "performance", "training",
    "practice", "competition", "tournament", "match", "pool", "open", "water", "outdoor", "indoor",
    "gym", "workout", "fitness", "running", "kids", "kid", "children", "boys", "girls", "women",
    "womens", "ladies", "men", "mens", "adult", "adults", "unisex", "junior", "senior", "silicone",
    "breathable", "quick", "dry", "soft", "strong", "sturdy", "official", "original", "genuine",
    "athletic", "sportswear", "activewear", "stylish", "elegant", "classic", "new", "latest",
    "certified", "approved", "grade", "heavy", "duty", "long", "lasting", "free", "non", "slip",
}
# Competitor-consensus words we accept: only words that say which sport/category the
# product belongs to. Features, materials and included items are never taken from competitors.
SEARCH_WORDS = {
    "swimming", "swim", "table", "tennis", "tt", "cricket", "football", "basketball", "volleyball",
    "hockey", "carrom", "chess", "skipping", "badminton", "sports", "sport", "dart", "darts",
}
# Audience / use phrases allowed in Amazon-style titles (search terms, not product claims).
AUDIENCE_USE = {"men", "mens", "women", "womens", "kids", "adults", "adult", "unisex", "ladies", "pool",
                "indoor", "outdoor", "practice", "play", "training", "gym", "workout", "match", "game",
                "home", "family", "street", "ground"}
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from title_reference_100 import TITLES as REFERENCE_TITLES
except Exception:  # noqa: BLE001
    REFERENCE_TITLES = {}
STRUCTURAL = {"a", "an", "and", "by", "for", "in", "of", "the", "with", "to", "on", "size", "colour",
              "color", "pack", "piece", "pc", "set"}
SYNONYMS = [
    {"goggle", "goggles"}, {"swim", "swimming"}, {"cap", "caps"}, {"tshirt", "t", "shirt", "tee"},
    {"pant", "pants", "lower", "lowers", "trackpant", "trackpants", "track"},
    {"racket", "racquet", "rackets", "racquets"}, {"ball", "balls"}, {"bat", "bats"},
    {"dumbbell", "dumbbells", "dumbell", "dumbells"}, {"rope", "ropes"}, {"jersey", "jerseys"},
    {"tt", "table", "tennis"}, {"carrom", "carom"}, {"board", "boards"}, {"coin", "coins"},
    {"striker", "strikers"}, {"chess"}, {"sleeve", "sleeves"}, {"men", "mens"},
]
PRODUCT_NOUNS = {
    "goggle", "goggles", "cap", "caps", "mask", "racket", "racquet", "ball", "balls", "bat", "shoe",
    "shoes", "shorts", "tshirt", "jersey", "lower", "pant", "pants", "trackpants", "gloves", "glove",
    "helmet", "rope", "dumbbell", "dumbbells", "board", "coin", "coins", "striker", "net", "bottle",
    "bag", "costume", "swimsuit", "kickboard", "fins", "earplugs", "earplug", "noseclip", "cover",
    "stand", "powder", "dartboard", "volleyball", "basketball", "football", "shuttlecock", "jacket",
    "hoodie", "sweatshirt", "trophy", "grip", "guard", "pad", "pads", "tube", "band", "mat", "kit",
}


# ---------------------------------------------------------------- text helpers
def clean(text):
    if text is None:
        return ""
    s = str(text)
    s = (s.replace("‑", "-").replace("‐", "-").replace("–", "-")
          .replace("—", "-").replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"'))
    return " ".join(re.sub(r"[^\x00-\x7F]+", " ", s).split())


def norm(text):
    return " ".join(re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", clean(text).casefold()))


def tokens(text):
    return norm(text).split()


def fact(value):
    v = clean(value)
    return "" if v.upper() in EMPTY_VALUES else v


def numbers_in(text):
    return set(re.findall(r"\d+(?:\.\d+)?", clean(text)))


def expand(words):
    out = set(words) | {w + "s" for w in words} | {w[:-1] for w in words if w.endswith("s") and len(w) > 3}
    for w in list(words):
        for group in SYNONYMS:
            if w in group:
                out |= group
    return out


def name_core(name):
    """Product name without a marketing tail after '|'."""
    return clean(name).split("|")[0].strip(" -")


# ---------------------------------------------------------------- inputs
def load_env(path):
    values = {}
    try:
        from dotenv import dotenv_values
        values = {k: v for k, v in dotenv_values(path).items() if v is not None}
    except Exception:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        values[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME", "GROQ_API_KEY"):
        if os.getenv(k) and k not in values:
            values[k] = os.getenv(k)
    return values


def load_skus(path):
    with open(path, encoding="utf-8") as f:
        raw = re.split(r"[,\s]+", f.read())
    seen, out = set(), []
    for s in raw:
        s = s.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def load_master(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    idx = {h: i for i, h in enumerate(header)}
    cols = {"brand": "Brand Name", "category": "Product Category", "colour": "Colour", "size": "Size",
            "invoice_description": "Product Description on Invoice", "website_name": "Name On Brand WebSite"}
    sku_i = idx["SKU ID for Market Places"]
    out = {}
    for r in rows:
        sku = clean(r[sku_i]) if r[sku_i] is not None else ""
        if sku and sku not in out:
            out[sku] = {k: (fact(r[idx[c]]) if c in idx else "") for k, c in cols.items()}
    wb.close()
    return out


class ReadOnlyDB:
    def __init__(self, conn, placeholder="%s", mysql=True):
        self.conn, self.ph = conn, placeholder
        if mysql:
            cur = conn.cursor()
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.execute("START TRANSACTION READ ONLY")
            cur.close()

    def select(self, sql, params=()):
        if not sql.lstrip().upper().startswith("SELECT"):
            raise RuntimeError("Read-only phase refused a non-SELECT statement.")
        if self.ph != "%s":
            sql = sql.replace("%s", self.ph)
        cur = self.conn.cursor()
        cur.execute(sql, tuple(params))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
        return rows

    def close(self):
        try:
            self.conn.rollback()
        finally:
            self.conn.close()


def mysql_connect(env):
    import pymysql
    return pymysql.connect(host=env.get("DB_HOST", "localhost"), port=int(env.get("DB_PORT", 3306)),
                           user=env.get("DB_USER", "root"), password=env.get("DB_PASSWORD", ""),
                           database=env.get("DB_NAME", "marketlens"), charset="utf8mb4", autocommit=False)


def fetch(db, skus):
    q = "(" + ", ".join(["%s"] * len(skus)) + ")"
    products = {r["asin"]: r for r in db.select(
        f"SELECT id, asin, product_name, category FROM products WHERE asin IN {q}", skus)}
    fpd = {r["sku_id"]: r for r in db.select(
        f"SELECT sku_id, product_name, final_product_title, all_keywords FROM final_product_data WHERE sku_id IN {q}", skus)}
    comps = defaultdict(list)
    for r in db.select(
            "SELECT source_product_asin, competitor_rank, competitor_title FROM competitor_products "
            f"WHERE source_product_asin IN {q} ORDER BY source_product_asin, competitor_rank", skus):
        t = clean(r["competitor_title"])
        if t and not re.fullmatch(r"Product [A-Z0-9]{10}", t) and t not in comps[r["source_product_asin"]]:
            comps[r["source_product_asin"]].append(t)
    taken = {norm(r["final_product_title"]) for r in db.select(
        "SELECT final_product_title FROM final_product_data WHERE final_product_title IS NOT NULL")
        if r["final_product_title"] and norm(r["final_product_title"]) != norm(MANUAL)}
    return products, fpd, comps, taken


# ---------------------------------------------------------------- vocabulary
def consensus_terms(comp_titles, source_tok, min_titles=3):
    """Words appearing in >= min_titles competitor titles, minus claims and competitor brands."""
    counts = Counter()
    for t in comp_titles:
        counts.update(set(tokens(t)))
    comp_brands = {tokens(t)[0] for t in comp_titles if tokens(t)} - source_tok
    out = []
    for w, c in counts.most_common():
        if c < min_titles or w not in SEARCH_WORDS or w in comp_brands:
            continue
        if any(ch.isdigit() for ch in w) or len(w) < 3:
            continue
        out.append(w)
    return out[:25], comp_brands


def build_context(sku, product, facts, comp_titles, keywords=""):
    name = clean(product["product_name"]) if product else facts.get("website_name", "")
    core = name_core(name)
    category = facts.get("category") or (clean(product.get("category")) if product else "")
    source_text = " ".join([name, category, facts.get("brand", ""), facts.get("invoice_description", ""),
                            facts.get("website_name", "")])
    source_tok = set(tokens(source_text))
    consensus, comp_brands = consensus_terms(comp_titles, source_tok)
    return {
        "sku": sku, "name": name, "core": core, "category": category, "brand": facts.get("brand", ""),
        "invoice": facts.get("invoice_description", ""), "source_text": source_text,
        "source_tok": source_tok, "consensus": consensus, "comp_brands": comp_brands,
        "comp_titles": comp_titles,
        "reference": REFERENCE_TITLES.get(sku, ""),
        "keywords": keywords,
        "extra_vocab": set(tokens(REFERENCE_TITLES.get(sku, ""))) | set(tokens(keywords)) | AUDIENCE_USE,
    }


# ---------------------------------------------------------------- validation
def validate_base(title, ctx):
    """Return list of rejection reasons for a BASE title (before colour/size are appended)."""
    reasons = []
    t = clean(title).strip('"').strip("'").strip()
    if not t or norm(t) == norm(MANUAL):
        return ["empty_or_manual"]
    if "\n" in title or "|" in t or "*" in t or "#" in t or "`" in t:
        reasons.append("format_not_clean")
    if len(t) < 60:
        reasons.append("too_short")
    if len(t) > 170:
        reasons.append("too_long")
    if norm(t) == norm(ctx["name"]) or norm(t) == norm(ctx["core"]):
        reasons.append("same_as_product_name")
    tt = tokens(t)
    tset = set(tt)

    brand = norm(ctx["brand"])
    if brand and brand not in norm(t):
        reasons.append("brand_missing")
    core_tok = tokens(ctx["core"])
    for w in core_tok:  # model / series codes with digits must stay
        if any(ch.isdigit() for ch in w) and w not in tset and w not in norm(t):
            reasons.append(f"model_code_missing:{w}")
    noise = STRUCTURAL | {"single"}
    important = [w for w in core_tok if w not in noise and not w.isdigit()]
    if important:
        covered = sum(1 for w in important if w in expand(tset))
        if covered / len(important) < 0.7:
            missing = [w for w in important if w not in expand(tset)]
            reasons.append("name_words_missing:" + "/".join(missing[:5]))

    extra = ctx.get("extra_vocab", set())
    allowed = expand(ctx["source_tok"]) | expand(set(ctx["consensus"])) | STRUCTURAL | expand(extra)
    ref_tok = expand(set(tokens(ctx.get("reference", ""))))
    claims = sorted({w for w in tset if w in CLAIM_WORDS and w not in AUDIENCE_USE
                     and w not in expand(ctx["source_tok"]) and w not in ref_tok})
    if claims:
        reasons.append("unverified_claim:" + "/".join(claims))
    brands = sorted({w for w in tset if w in ctx["comp_brands"]})
    if brands:
        reasons.append("competitor_brand:" + "/".join(brands))
    other_types = sorted({w for w in tset if w in PRODUCT_NOUNS and w not in allowed})
    if other_types:
        reasons.append("different_product_type:" + "/".join(other_types))
    unknown = sorted({w for w in tset if w not in allowed and w not in CLAIM_WORDS
                      and w not in ctx["comp_brands"] and w not in PRODUCT_NOUNS
                      and not any(ch.isdigit() for ch in w)})
    if unknown:
        reasons.append("unsupported_words:" + "/".join(unknown[:6]))
    invented = sorted(numbers_in(t) - numbers_in(ctx["source_text"]))
    if invented:
        reasons.append("invented_number:" + "/".join(invented))
    stem = lambda w: w[:-1] if w.endswith("s") and len(w) > 3 else w
    name_counts = Counter(stem(w) for w in tokens(ctx["name"]))
    for w, n in Counter(stem(w) for w in tokens(ctx.get("reference", ""))).items():
        name_counts[w] = max(name_counts[w], n)
    repeated = sorted(w for w, n in Counter(stem(w) for w in tt).items()
                      if n > 1 and n > name_counts.get(w, 0) and w not in STRUCTURAL)
    if repeated or re.search(r"\b(\w+)\s+\1\b", t, flags=re.I):
        reasons.append("repeated_word" + (":" + "/".join(repeated) if repeated else ""))
    for c in ctx["comp_titles"]:
        if SequenceMatcher(None, norm(t), norm(c)).ratio() >= 0.85:
            reasons.append("near_competitor_copy")
            break
    return reasons


def contains_phrase(text, phrase):
    """True if the tokens of phrase appear consecutively in text (whole words only)."""
    t, p = tokens(text), tokens(phrase)
    if not p:
        return True
    return any(t[i:i + len(p)] == p for i in range(len(t) - len(p) + 1))


def add_variant(base, colour, size):
    """Append verified colour / size unless already present as whole words."""
    out = clean(base).rstrip(" ,-")
    parts = []
    if colour and not contains_phrase(out, colour):
        parts.append(colour)
    if size:
        if re.search(r"\d", size):
            present = norm(size).replace(" ", "") in norm(out).replace(" ", "")
        else:
            present = contains_phrase(out, f"size {size}")
        if not present:
            parts.append(size if re.search(r"\d", size) else f"Size {size}")
    if parts:
        out = f"{out} - {', '.join(parts)}"
    return out


def template_title(ctx):
    """Non-AI title from verified facts only."""
    core = ctx["core"]
    brand = ctx["brand"]
    if core.isupper():  # avoid ALL-CAPS titles; keep brand and model codes as written
        keep = set(tokens(brand))
        core = " ".join(w if (norm(w) in keep or any(ch.isdigit() for ch in w) or len(w) <= 2)
                        else w.capitalize() for w in core.split())
    title = core
    if brand and norm(brand) not in norm(core):
        title = f"{brand} {core}"
    cat = ctx["category"]
    generic = {"apparel", "gym training", "swimming accessories", "accessories", "shoe"}
    cat_tok = set(tokens(cat))
    if cat and norm(cat) not in generic and not (cat_tok <= expand(set(tokens(title)))):
        if not any(t in {"borad", "stirkcer", "hocky"} for t in cat_tok):
            title = f"{title} {cat}"
    return clean(title)


# ---------------------------------------------------------------- Groq
class GroqPool:
    def __init__(self, api_key, models, max_wait, delay, client=None):
        if client is None:
            from groq import Groq
            client = Groq(api_key=api_key, max_retries=0)
        self.client = client
        self.models = list(models)
        self.cool_until = {m: 0.0 for m in self.models}
        self.dead = set()
        self.max_wait = max_wait
        self.delay = delay
        self.requests = 0
        self.stopped = None

    @staticmethod
    def _wait_seconds(exc):
        headers = getattr(getattr(exc, "response", None), "headers", None) or {}
        for key, scale in (("retry-after-ms", 1000.0), ("retry-after", 1.0)):
            try:
                v = headers.get(key)
                if v:
                    return float(v) / scale
            except (TypeError, ValueError):
                pass
        return 60.0

    def available(self):
        now = time.time()
        return [m for m in self.models if m not in self.dead and self.cool_until[m] <= now]

    def ask(self, messages, preferred=None):
        """Return (text, model) or (None, reason). Rotates models on rate limits."""
        while True:
            live = [m for m in self.models if m not in self.dead]
            if not live:
                self.stopped = "no_working_models"
                return None, self.stopped
            avail = self.available()
            if not avail:
                wait = min(self.cool_until[m] for m in live) - time.time()
                if wait > self.max_wait:
                    self.stopped = f"all_models_cooling ({wait:.0f}s)"
                    return None, self.stopped
                print(f"      all models rate-limited, waiting {wait:.0f}s", flush=True)
                time.sleep(max(wait, 1))
                continue
            model = preferred if preferred in avail else avail[0]
            kwargs = {"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 700}
            if model.startswith("openai/gpt-oss"):
                kwargs["reasoning_effort"] = "low"
                kwargs["max_tokens"] = 1200
            try:
                self.requests += 1
                r = self.client.chat.completions.create(**kwargs)
                time.sleep(self.delay)
                text = (r.choices[0].message.content or "").strip()
                if not text:
                    return None, "empty_response"
                return text, model
            except Exception as e:  # noqa: BLE001
                status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
                if status == 429 or type(e).__name__ == "RateLimitError":
                    wait = self._wait_seconds(e)
                    self.cool_until[model] = time.time() + wait
                    print(f"      429 on {model} (wait {wait:.0f}s) -> trying another model", flush=True)
                    continue
                if status in (400, 404):
                    msg = str(e).lower()
                    if "reasoning" in msg and "reasoning_effort" in kwargs:
                        self.models = [m for m in self.models]  # keep model, retry without param
                        try:
                            kwargs.pop("reasoning_effort", None)
                            self.requests += 1
                            r = self.client.chat.completions.create(**kwargs)
                            text = (r.choices[0].message.content or "").strip()
                            return (text, model) if text else (None, "empty_response")
                        except Exception:  # noqa: BLE001
                            pass
                    print(f"      {model} unavailable ({status}) -> skipped for this run", flush=True)
                    self.dead.add(model)
                    continue
                if status in (401, 403):
                    self.stopped = f"auth_error_{status}"
                    return None, self.stopped
                self.stopped = f"api_error_{status or type(e).__name__}"
                return None, self.stopped


def build_prompt(ctx):
    comps = "\n".join(f"- {t}" for t in ctx["comp_titles"][:8])
    ref = ctx.get("reference", "")
    kw = ", ".join(k.strip() for k in (ctx.get("keywords") or "").split(",")[:12] if k.strip())
    facts = [f"- Product name: {ctx['name']}", f"- Brand: {ctx['brand'] or '(see name)'}"]
    if ctx["category"]:
        facts.append(f"- Category: {ctx['category']}")
    if ctx["invoice"]:
        facts.append(f"- Internal description: {ctx['invoice']}")
    terms = ", ".join(ctx["consensus"]) or "(none)"
    style = (f"\nStyle example for THIS product (write your own wording in this style, without colour/size):\n{ref}\n"
             if ref else "")
    return f"""Write ONE keyword-rich, impressive Amazon India product title for OUR product, in the same style as top Amazon competitor titles.

OUR VERIFIED FACTS (the only facts you may state):
{chr(10).join(facts)}

Competitor titles (copy only their STRUCTURE and word order, never their facts or brands):
{comps}

Common search words in competitor titles that you MAY use if they describe what our product is: {terms}
Customer search keywords for our product (use the relevant ones naturally): {kw or "(none)"}
{style}
Rules:
1. Format: Brand + series/model + product type, then 2-3 comma-separated search phrases (who it is for, where it is used). 80-160 characters.
2. Keep the brand, every model/series code and the product type from our product name.
3. Do NOT include colour or size; they are added automatically afterwards.
4. Audience and use phrases are allowed (for Men and Women, for Kids and Adults, Swimming Pool, Indoor and Outdoor Play, Gym Workout). Do NOT claim materials or features that are not in our facts (silicone, anti-fog, UV protection, waterproof, polarized, magnetic, foldable, premium, durable, lightweight, professional).
5. No competitor brand names, no new numbers, no "|", no quotes, no explanation.
6. If no safe title is possible, output exactly: {MANUAL}
Output ONLY the title."""


def generate_base(pool, ctx):
    """Up to 3 Groq attempts with targeted repair. Returns (title|None, model, reason)."""
    messages = [{"role": "system", "content": "You write truthful, concise Amazon product titles."},
                {"role": "user", "content": build_prompt(ctx)}]
    last_reason, model_used = "", ""
    for attempt in range(3):
        text, model = pool.ask(messages)
        if text is None:
            return None, model_used, model  # model holds stop/error reason
        model_used = model
        title = clean(text.splitlines()[0]).strip('"').strip("'").strip()
        if norm(title) == norm(MANUAL):
            return None, model, "groq_returned_manual"
        reasons = validate_base(title, ctx)
        if not reasons:
            return title, model, "ok" if attempt == 0 else f"ok_after_repair_{attempt}"
        last_reason = "; ".join(reasons)
        print(f"      rejected ({last_reason}) -> repair", flush=True)
        messages = messages + [
            {"role": "assistant", "content": title},
            {"role": "user", "content": f"Rejected because: {last_reason}. Fix exactly these problems. "
                                        "Remove every word that is not in our facts or the allowed search words. "
                                        "Output ONLY the corrected title."},
        ]
    return None, model_used, "validation_failed: " + last_reason


# ---------------------------------------------------------------- run
CSV_COLS = ["sku_id", "product_name", "status", "final_title", "base_title", "model", "reason", "flags",
            "colour_used", "size_used", "competitor_titles", "approve"]


def run_generate(args, db=None, groq_client=None):
    skus = load_skus(args.skus_file)
    master = load_master(args.master)
    env = load_env(os.path.join(PROJECT_ROOT, ".env"))
    own_db = db is None
    if own_db:
        db = ReadOnlyDB(mysql_connect(env))
    try:
        products, fpd, comps, taken = fetch(db, skus)
    finally:
        if own_db:
            db.close()

    out_dir = args.out_dir or os.path.join(PROJECT_ROOT, "scratch", f"fast_titles_{datetime.now():%Y%m%d_%H%M%S}")
    os.makedirs(out_dir, exist_ok=True)
    progress_path = os.path.join(out_dir, "progress.json")
    progress = {}
    if os.path.exists(progress_path):
        with open(progress_path, encoding="utf-8") as f:
            progress = json.load(f)
        print(f"Resuming: {len(progress)} SKUs already in progress.json")

    # groups of same-name SKUs share one Groq base title
    groups = defaultdict(list)
    for s in skus:
        p = products.get(s)
        name = clean(p["product_name"]) if p else master.get(s, {}).get("website_name", s)
        groups[norm(name)].append(s)

    pool = None
    if not args.dry_run:
        key = env.get("GROQ_API_KEY", "").strip()
        if groq_client is None and (not key or key == "your_groq_api_key_here"):
            print("GROQ_API_KEY not configured in .env")
            return None
        pool = GroqPool(key, [m.strip() for m in args.models.split(",") if m.strip()],
                        args.max_wait, args.delay, client=groq_client)

    used_titles = set(taken)
    for rec in progress.values():
        if rec.get("status") in ("AI_VALID", "FALLBACK", "TEMPLATE") and rec.get("final_title"):
            used_titles.add(norm(rec["final_title"]))

    def save():
        with open(progress_path, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)

    done_groups = 0
    for gkey, members in groups.items():
        lead0 = members[0]
        ctx0 = build_context(lead0, products.get(lead0), master.get(lead0, {}), comps.get(lead0, []),
                             keywords_cell(fpd[lead0]["all_keywords"]) if fpd.get(lead0) else "")

        def needs(s):
            rec0 = progress.get(s)
            if not rec0:
                return True
            st = rec0.get("status")
            if st in ("KEPT_EXISTING", "MANUAL"):
                return False
            if st in ("TEMPLATE", "FALLBACK"):
                return args.retry_templates
            if st == "AI_VALID":
                return bool(validate_base(rec0.get("base_title", ""), ctx0))  # recheck with current rules
            return True

        todo = [s for s in members if needs(s)]
        if not todo:
            continue
        for s in todo:
            old = progress.get(s, {}).get("final_title")
            if old:
                used_titles.discard(norm(old))
        lead = todo[0]
        p = products.get(lead)
        facts = master.get(lead, {})
        lead_kw = keywords_cell(fpd[lead]["all_keywords"]) if fpd.get(lead) else ""
        ctx = build_context(lead, p, facts, comps.get(lead, []), lead_kw)
        print(f"[{done_groups + 1}] {ctx['name']}  ({len(members)} SKU{'s' if len(members) > 1 else ''})", flush=True)

        base, model, reason = None, "", ""
        need_ai = [s for s in todo if not (fpd.get(s) and fpd[s]["final_product_title"]
                                           and norm(fpd[s]["final_product_title"]) != norm(MANUAL))]
        if args.dry_run:
            reason = "dry_run"
        elif need_ai and not ctx["comp_titles"]:
            reason = "no_competitor_titles"
        elif need_ai and pool.stopped is None:
            base, model, reason = generate_base(pool, ctx)

        for s in members:
            if s not in todo:
                continue
            p = products.get(s)
            f = master.get(s, {})
            name = clean(p["product_name"]) if p else f.get("website_name", "")
            existing = fpd.get(s, {}).get("final_product_title") if fpd.get(s) else None
            flags = []
            colour = f.get("colour", "")
            if colour and norm(colour) in {norm(c) for c in SUSPECT_COLOURS}:
                flags.append(f"master_colour_suspect:{colour}")
                colour = ""
            size = f.get("size", "")
            rec = {"sku_id": s, "product_name": name, "colour_used": colour, "size_used": size,
                   "competitor_titles": len(comps.get(s, [])), "model": model, "base_title": base or "",
                   "approve": ""}
            if existing and norm(existing) != norm(MANUAL):
                rec.update(status="KEPT_EXISTING", final_title=clean(existing), reason="existing_title_not_regenerated")
            elif not p:
                rec.update(status="MANUAL", final_title="", reason="not_in_products_table")
            elif len(members) > 1 and any("master_colour_suspect" in x for x in flags) and not size:
                rec.update(status="MANUAL", final_title="", reason="variant_colour_suspect_cannot_distinguish")
            elif args.dry_run:
                rec.update(status="DRY_RUN", final_title=add_variant(template_title(build_context(s, p, f, comps.get(s, []))), colour, size),
                           reason="dry_run_template_preview")
            else:
                if base:
                    title = add_variant(base, colour, size)
                    status = "AI_VALID"
                elif REFERENCE_TITLES.get(s):
                    title = REFERENCE_TITLES[s]
                    status = "FALLBACK"
                else:
                    title = add_variant(template_title(build_context(s, p, f, comps.get(s, []))), colour, size)
                    status = "TEMPLATE"
                    flags.append(f"ai_failed:{reason}")
                if len(title) > 200:
                    title = title[:200].rsplit(" ", 1)[0]
                    flags.append("trimmed_to_200")
                if len(title) < 60:
                    flags.append("short_title")
                if norm(title) in used_titles:
                    rec.update(status="MANUAL", final_title="", reason="duplicate_title", base_title=base or "")
                else:
                    used_titles.add(norm(title))
                    rec.update(status=status, final_title=title, reason=reason)
            rec["flags"] = "; ".join(flags)
            progress[s] = rec
            print(f"      {s}: {rec['status']} -> {rec['final_title']}", flush=True)
        save()
        write_outputs(out_dir, skus, progress, products, fpd, master)
        done_groups += 1
        if pool is not None and pool.stopped:
            print(f"\nGroq stopped: {pool.stopped}. Remaining SKUs get TEMPLATE titles; re-run later with "
                  f"--out-dir {out_dir} --retry-templates to try AI again.", flush=True)

    write_outputs(out_dir, skus, progress, products, fpd, master)
    counts = Counter(progress[s]["status"] for s in skus if s in progress)
    print("\n" + "=" * 70)
    print("SUMMARY:", dict(counts))
    if pool is not None:
        print(f"Groq requests: {pool.requests} | models skipped: {sorted(pool.dead) or 'none'}")
    print(f"Review CSV : {os.path.join(out_dir, 'titles_review.csv')}")
    print(f"Excel      : {os.path.join(out_dir, 'Final_Product_Data_100.xlsx')}")
    print("Database writes: NONE. After review run --apply <csv> to save titles.")
    return out_dir


def keywords_cell(val):
    if val is None:
        return ""
    if isinstance(val, (bytes, str)):
        try:
            val = json.loads(val)
        except Exception:
            return str(val)
    if isinstance(val, list):
        return ", ".join(str(x) for x in val)
    return str(val)


def write_outputs(out_dir, skus, progress, products, fpd, master):
    with open(os.path.join(out_dir, "titles_review.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for s in skus:
            if s in progress:
                w.writerow(progress[s])
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Final Product Data"
    ws.append(["product_name", "sku_id", "final_product_title", "all_keywords"])
    for s in skus:
        rec = progress.get(s, {})
        p = products.get(s)
        name = clean(p["product_name"]) if p else master.get(s, {}).get("website_name", "")
        title = rec.get("final_title") or MANUAL
        kws = keywords_cell(fpd[s]["all_keywords"]) if fpd.get(s) else ""
        ws.append([name, s, title, kws])
    wb.save(os.path.join(out_dir, "Final_Product_Data_100.xlsx"))


def run_apply(args, conn=None):
    with open(args.apply, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    todo = [r for r in rows if r.get("status") in ("AI_VALID", "FALLBACK", "TEMPLATE") and r.get("final_title")
            and (r.get("approve") or "").strip().lower() not in ("no", "n", "0")]
    print(f"Rows to write: {len(todo)} (skipped {len(rows) - len(todo)})")
    if not todo:
        return 0
    env = load_env(os.path.join(PROJECT_ROOT, ".env"))
    own = conn is None
    if own:
        conn = mysql_connect(env)
    ph = "%s" if own else "?"
    written = 0
    try:
        cur = conn.cursor()
        for r in todo:
            cur.execute(
                f"UPDATE final_product_data SET final_product_title = {ph} "
                f"WHERE sku_id = {ph} AND final_product_title = {ph}",
                (r["final_title"].strip(), r["sku_id"].strip(), MANUAL))
            written += cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()
    print(f"Titles written: {written}. Only final_product_title changed; rows that were not "
          f"{MANUAL} were left untouched.")
    return written


def main(argv=None, db=None, groq_client=None, apply_conn=None):
    ap = argparse.ArgumentParser(description="Fast title generation for a SKU list")
    ap.add_argument("--skus-file", default=os.path.join(PROJECT_ROOT, "scratch", "skus_100.txt"))
    ap.add_argument("--master", default=os.path.join(PROJECT_ROOT, "22Y_SKU_Master_Updated.xlsx"))
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--models", default=DEFAULT_MODELS)
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between Groq calls")
    ap.add_argument("--max-wait", type=float, default=420, help="max seconds to wait when ALL models are rate-limited")
    ap.add_argument("--dry-run", action="store_true", help="no Groq calls; template preview only")
    ap.add_argument("--retry-templates", action="store_true", help="on resume, retry AI for TEMPLATE rows")
    ap.add_argument("--apply", help="write reviewed titles from this CSV into final_product_data")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.apply:
        return run_apply(args, conn=apply_conn)
    return run_generate(args, db=db, groq_client=groq_client)


if __name__ == "__main__":
    main()
