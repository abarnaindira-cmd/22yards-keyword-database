import json

with open("scratch/preflight_rollback_snapshot.json", "r", encoding="utf-8") as f:
    snapshot = json.load(f)

exact_in_snapshot = [item for item in snapshot if item["product_name"] == item["final_product_title"]]
print(f"Total Snapshot Records: {len(snapshot)}")
print(f"Exact Original Name Records in Snapshot: {len(exact_in_snapshot)}")

sample = exact_in_snapshot[:5]
for s in sample:
    print(f"SKU: {s['sku_id']} | Name: {s['product_name']} | Title: {s['final_product_title']}")
