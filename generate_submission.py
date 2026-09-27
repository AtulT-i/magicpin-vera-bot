"""
magicpin AI Challenge — Generate submission.jsonl
=================================================

Loads the 30 canonical test pairs from dataset/expanded/test_pairs.json,
runs bot.compose() for each pair across the 4-context framework, and outputs
the official 30-line submission.jsonl file.
"""

import json
from pathlib import Path
import bot

BASE_DIR = Path(__file__).parent
EXPANDED_DIR = BASE_DIR / "dataset" / "expanded"


def load_dataset():
    categories = {}
    merchants = {}
    customers = {}
    triggers = {}

    cat_dir = EXPANDED_DIR / "categories"
    if cat_dir.exists():
        for f in cat_dir.glob("*.json"):
            d = json.load(open(f, encoding="utf-8"))
            categories[d.get("slug", f.stem)] = d

    m_dir = EXPANDED_DIR / "merchants"
    if m_dir.exists():
        for f in m_dir.glob("*.json"):
            d = json.load(open(f, encoding="utf-8"))
            merchants[d.get("merchant_id", f.stem)] = d

    c_dir = EXPANDED_DIR / "customers"
    if c_dir.exists():
        for f in c_dir.glob("*.json"):
            d = json.load(open(f, encoding="utf-8"))
            customers[d.get("customer_id", f.stem)] = d

    t_dir = EXPANDED_DIR / "triggers"
    if t_dir.exists():
        for f in t_dir.glob("*.json"):
            d = json.load(open(f, encoding="utf-8"))
            triggers[d.get("id", f.stem)] = d

    return categories, merchants, customers, triggers


def main():
    categories, merchants, customers, triggers = load_dataset()
    test_pairs_path = EXPANDED_DIR / "test_pairs.json"

    if not test_pairs_path.exists():
        print(f"Error: {test_pairs_path} not found. Run dataset generator first.")
        return

    test_data = json.load(open(test_pairs_path, encoding="utf-8"))
    pairs = test_data.get("pairs", [])
    print(f"Generating compositions for {len(pairs)} test pairs...")

    output_lines = []
    for pair in pairs:
        test_id = pair.get("test_id")
        tid = pair.get("trigger_id")
        mid = pair.get("merchant_id")
        cid = pair.get("customer_id")

        trig = triggers.get(tid, {"id": tid, "kind": "general_nudge", "payload": {}})
        merchant = merchants.get(mid, {"merchant_id": mid, "identity": {"name": "Merchant"}})
        cat_slug = merchant.get("category_slug") or trig.get("payload", {}).get("category", "restaurants")
        category = categories.get(cat_slug, {"slug": cat_slug})
        customer = customers.get(cid) if cid else None

        composed = bot.compose(category, merchant, trig, customer)

        row = {
            "test_id": test_id,
            "body": composed["body"],
            "cta": composed["cta"],
            "send_as": composed["send_as"],
            "suppression_key": composed["suppression_key"],
            "rationale": composed["rationale"],
        }
        output_lines.append(row)

    out_file = BASE_DIR / "submission.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for item in output_lines:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Successfully generated {len(output_lines)} test submissions to {out_file}")


if __name__ == "__main__":
    main()
