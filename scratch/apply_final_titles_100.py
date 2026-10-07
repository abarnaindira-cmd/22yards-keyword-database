"""
Save the reviewed Amazon titles (scratch/title_reference_100.py) for the 100 confirmed SKUs
into MySQL final_product_data.final_product_title.

  python scratch/apply_final_titles_100.py

What it does:
  1. Backs up the current final_product_data rows of these SKUs to
     scratch/final_titles_backup_<timestamp>.json (rollback point).
  2. Updates ONLY final_product_title for these SKUs. product_name and all_keywords are untouched.
     No other SKU is touched. No schema change. No Groq call.
  3. Reads the rows back and verifies every title.

Rollback:  python scratch/apply_final_titles_100.py --restore scratch/final_titles_backup_<timestamp>.json
"""
import argparse
import json
import os
import sys
from datetime import datetime, date
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)


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
    return values


def connect(env):
    import pymysql
    return pymysql.connect(host=env.get("DB_HOST", "localhost"), port=int(env.get("DB_PORT", 3306)),
                           user=env.get("DB_USER", "root"), password=env.get("DB_PASSWORD", ""),
                           database=env.get("DB_NAME", "marketlens"), charset="utf8mb4", autocommit=False)


def _default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, bytes):
        return o.decode("utf-8", "replace")
    return str(o)


def fetch(cur, ph, skus):
    q = "(" + ", ".join([ph] * len(skus)) + ")"
    cur.execute(f"SELECT sku_id, product_name, final_product_title, all_keywords FROM final_product_data "
                f"WHERE sku_id IN {q}", tuple(skus))
    cols = [d[0] for d in cur.description]
    return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}


def apply(conn, titles, ph="%s", backup_dir=None):
    skus = list(titles)
    cur = conn.cursor()
    before = fetch(cur, ph, skus)
    missing = [s for s in skus if s not in before]

    backup_dir = backup_dir or HERE
    backup = os.path.join(backup_dir, f"final_titles_backup_{datetime.now():%Y%m%d_%H%M%S}.json")
    with open(backup, "w", encoding="utf-8") as f:
        json.dump({"created_at": datetime.now().isoformat(timespec="seconds"),
                   "rows": list(before.values())}, f, indent=2, ensure_ascii=False, default=_default)
    print(f"Backup of {len(before)} current rows: {backup}")

    updated = 0
    try:
        for sku in skus:
            if sku in missing:
                continue
            cur.execute(f"UPDATE final_product_data SET final_product_title = {ph} WHERE sku_id = {ph}",
                        (titles[sku], sku))
            updated += 1
        conn.commit()
    except Exception:
        conn.rollback()
        print("ERROR: nothing was saved (rolled back).")
        raise

    after = fetch(cur, ph, skus)
    wrong = [s for s in skus if s not in missing and (after.get(s) or {}).get("final_product_title") != titles[s]]
    kw_changed = [s for s in skus if s in before and after[s]["all_keywords"] != before[s]["all_keywords"]]
    print(f"Updated titles : {updated}")
    print(f"Verified OK    : {updated - len(wrong)}")
    if missing:
        print(f"Not in final_product_data (skipped): {missing}")
    if wrong:
        print(f"MISMATCH after save: {wrong}")
    print(f"all_keywords changed: {len(kw_changed)} (must be 0)")
    return updated, wrong, missing, backup


def restore(conn, backup_path, ph="%s"):
    with open(backup_path, encoding="utf-8") as f:
        rows = json.load(f)["rows"]
    cur = conn.cursor()
    try:
        for r in rows:
            cur.execute(f"UPDATE final_product_data SET final_product_title = {ph} WHERE sku_id = {ph}",
                        (r["final_product_title"], r["sku_id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    print(f"Restored final_product_title for {len(rows)} rows from {backup_path}")


def main(argv=None, conn=None, ph="%s"):
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", help="backup JSON to restore titles from")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    own = conn is None
    if own:
        conn = connect(load_env(os.path.join(PROJECT_ROOT, ".env")))
    try:
        if args.restore:
            restore(conn, args.restore, ph)
        else:
            from title_reference_100 import TITLES
            print(f"Saving {len(TITLES)} titles to final_product_data ...")
            apply(conn, TITLES, ph)
    finally:
        if own:
            conn.close()


if __name__ == "__main__":
    main()
