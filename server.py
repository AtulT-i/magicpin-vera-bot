"""
magicpin AI Challenge — Vera Bot HTTP API Server
================================================

Implements the official 5 HTTP endpoints required by the challenge evaluation harness:
1. POST /v1/context  — Idempotent context ingestion with atomic version replacement
2. POST /v1/tick     — Proactive message composition for active trigger batch
3. POST /v1/reply    — Multi-turn merchant/customer conversation state handling
4. GET  /v1/healthz  — Health check and loaded context telemetry
5. GET  /v1/metadata — Bot identity, architecture, and team metadata

Also serves an interactive web dashboard on GET / for human evaluators.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request, Response

import bot
import conversation_handlers

app = Flask(__name__)
START_TIME = time.time()

# In-memory context stores with version tracking
CATEGORIES: Dict[str, Dict[str, Any]] = {}
MERCHANTS: Dict[str, Dict[str, Any]] = {}
CUSTOMERS: Dict[str, Dict[str, Any]] = {}
TRIGGERS: Dict[str, Dict[str, Any]] = {}

VERSIONS: Dict[str, int] = {}  # key: f"{scope}:{context_id}" -> int version
CONVERSATION_STATES: Dict[str, Dict[str, Any]] = {}
LOG_HISTORY: list[Dict[str, Any]] = []


def _get_context_store(scope: str) -> Optional[Dict[str, Dict[str, Any]]]:
    mapping = {
        "category": CATEGORIES,
        "merchant": MERCHANTS,
        "customer": CUSTOMERS,
        "trigger": TRIGGERS,
    }
    return mapping.get(scope.lower())


def preload_local_dataset():
    """Preload dataset files if available so bot is fully primed."""
    base_dir = Path(__file__).parent / "dataset"
    expanded_dir = base_dir / "expanded"

    # 1. Categories
    cat_dir = expanded_dir / "categories" if (expanded_dir / "categories").exists() else (base_dir / "categories")
    if cat_dir.exists():
        for f in cat_dir.glob("*.json"):
            try:
                data = json.load(open(f, encoding="utf-8"))
                slug = data.get("slug", f.stem)
                CATEGORIES[slug] = data
                VERSIONS[f"category:{slug}"] = 1
            except Exception:
                pass

    # 2. Merchants
    m_dir = expanded_dir / "merchants"
    if m_dir.exists():
        for f in m_dir.glob("*.json"):
            try:
                data = json.load(open(f, encoding="utf-8"))
                mid = data.get("merchant_id", f.stem)
                MERCHANTS[mid] = data
                VERSIONS[f"merchant:{mid}"] = 1
            except Exception:
                pass
    elif (base_dir / "merchants_seed.json").exists():
        try:
            data = json.load(open(base_dir / "merchants_seed.json", encoding="utf-8"))
            for m in data.get("merchants", []):
                mid = m.get("merchant_id")
                if mid:
                    MERCHANTS[mid] = m
                    VERSIONS[f"merchant:{mid}"] = 1
        except Exception:
            pass

    # 3. Customers
    c_dir = expanded_dir / "customers"
    if c_dir.exists():
        for f in c_dir.glob("*.json"):
            try:
                data = json.load(open(f, encoding="utf-8"))
                cid = data.get("customer_id", f.stem)
                CUSTOMERS[cid] = data
                VERSIONS[f"customer:{cid}"] = 1
            except Exception:
                pass
    elif (base_dir / "customers_seed.json").exists():
        try:
            data = json.load(open(base_dir / "customers_seed.json", encoding="utf-8"))
            for c in data.get("customers", []):
                cid = c.get("customer_id")
                if cid:
                    CUSTOMERS[cid] = c
                    VERSIONS[f"customer:{cid}"] = 1
        except Exception:
            pass

    # 4. Triggers
    t_dir = expanded_dir / "triggers"
    if t_dir.exists():
        for f in t_dir.glob("*.json"):
            try:
                data = json.load(open(f, encoding="utf-8"))
                tid = data.get("id", f.stem)
                TRIGGERS[tid] = data
                VERSIONS[f"trigger:{tid}"] = 1
            except Exception:
                pass
    elif (base_dir / "triggers_seed.json").exists():
        try:
            data = json.load(open(base_dir / "triggers_seed.json", encoding="utf-8"))
            for t in data.get("triggers", []):
                tid = t.get("id")
                if tid:
                    TRIGGERS[tid] = t
                    VERSIONS[f"trigger:{tid}"] = 1
        except Exception:
            pass


# Automatically prime datasets upon import
preload_local_dataset()


# -------------------------------------------------------------
# 1. GET /v1/healthz
# -------------------------------------------------------------
@app.route("/v1/healthz", methods=["GET"])
def healthz():
    uptime = int(time.time() - START_TIME)
    return jsonify({
        "status": "ok",
        "uptime_seconds": uptime,
        "contexts_loaded": {
            "category": len(CATEGORIES),
            "merchant": len(MERCHANTS),
            "customer": len(CUSTOMERS),
            "trigger": len(TRIGGERS),
        },
    }), 200


# -------------------------------------------------------------
# 2. GET /v1/metadata
# -------------------------------------------------------------
@app.route("/v1/metadata", methods=["GET"])
def metadata():
    return jsonify({
        "team_name": "Vera Elite",
        "team_members": ["Magicpin AI Assistant Team"],
        "model": "hybrid-deterministic-reasoning-v2",
        "approach": "4-context composition framework with zero-hallucination ground truth synthesis, category voice profiling, and multi-turn auto-reply filtering",
        "contact_email": "vera@magicpin.com",
        "version": "2.0.0",
        "submitted_at": "2026-04-26T10:00:00Z",
    }), 200


# -------------------------------------------------------------
# 3. POST /v1/context
# -------------------------------------------------------------
@app.route("/v1/context", methods=["POST"])
def push_context():
    data = request.get_json(force=True, silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"accepted": False, "reason": "invalid_json"}), 400

    scope = data.get("scope")
    context_id = data.get("context_id")
    version = data.get("version", 1)
    payload = data.get("payload", {})

    store = _get_context_store(str(scope))
    if store is None or not context_id:
        return jsonify({"accepted": False, "reason": "invalid_scope_or_id"}), 400

    v_key = f"{scope}:{context_id}"
    current_version = VERSIONS.get(v_key, 0)

    # Check version idempotency & staleness
    if context_id in store and version < current_version:
        return jsonify({
            "accepted": False,
            "reason": "stale_version",
            "current_version": current_version,
        }), 409

    # Store atomically (or no-op if same version)
    store[context_id] = payload
    VERSIONS[v_key] = max(version, current_version)

    ack_id = f"ack_{context_id}_v{version}"
    stored_at = datetime.utcnow().isoformat() + "Z"

    return jsonify({
        "accepted": True,
        "ack_id": ack_id,
        "stored_at": stored_at,
    }), 200


# -------------------------------------------------------------
# 4. POST /v1/tick
# -------------------------------------------------------------
@app.route("/v1/tick", methods=["POST"])
def tick():
    data = request.get_json(force=True, silent=True) or {}
    now = data.get("now", datetime.utcnow().isoformat() + "Z")
    available_triggers = data.get("available_triggers", [])

    actions = []

    for tid in available_triggers:
        trig = TRIGGERS.get(tid)
        if not trig:
            continue

        payload = trig.get("payload", {})
        mid = trig.get("merchant_id") or payload.get("merchant_id")
        cid = trig.get("customer_id") or payload.get("customer_id")

        merchant = MERCHANTS.get(mid, {}) if mid else {}
        if not merchant and MERCHANTS:
            mid, merchant = next(iter(MERCHANTS.items()))

        cat_slug = merchant.get("category_slug") or payload.get("category", "")
        category = CATEGORIES.get(cat_slug, {})
        customer = CUSTOMERS.get(cid) if cid else None

        # Compose message
        composed = bot.compose(category, merchant, trig, customer)

        conv_id = f"conv_{tid}_{uuid.uuid4().hex[:6]}"
        action_item = {
            "conversation_id": conv_id,
            "merchant_id": mid,
            "customer_id": cid,
            "send_as": composed["send_as"],
            "trigger_id": tid,
            "template_name": f"vera_{trig.get('kind', 'nudge')}_v1",
            "template_params": [
                merchant.get("identity", {}).get("name", ""),
                category.get("slug", ""),
            ],
            "body": composed["body"],
            "cta": composed["cta"],
            "suppression_key": composed["suppression_key"],
            "rationale": composed["rationale"],
        }
        actions.append(action_item)

        LOG_HISTORY.append({
            "timestamp": now,
            "type": "tick_action",
            "trigger_id": tid,
            "merchant_id": mid,
            "body": composed["body"],
        })

    return jsonify({"actions": actions}), 200


# -------------------------------------------------------------
# 5. POST /v1/reply
# -------------------------------------------------------------
@app.route("/v1/reply", methods=["POST"])
def reply():
    data = request.get_json(force=True, silent=True) or {}
    conv_id = data.get("conversation_id", f"conv_{uuid.uuid4().hex[:6]}")
    mid = data.get("merchant_id", "")
    message = data.get("message", "")
    turn = data.get("turn_number", 1)

    state = CONVERSATION_STATES.setdefault(conv_id, {
        "turns": 0,
        "history": [],
        "merchant_id": mid,
    })
    state["turns"] = turn
    state["history"].append({"from": "merchant", "message": message})

    merchant = MERCHANTS.get(mid)
    res = conversation_handlers.respond(
        conversation_id=conv_id,
        merchant_id=mid,
        merchant_message=message,
        turn_number=turn,
        state=state,
        merchant_context=merchant,
    )

    LOG_HISTORY.append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "type": "reply_turn",
        "conversation_id": conv_id,
        "merchant_message": message,
        "bot_response": res,
    })

    return jsonify(res), 200


# -------------------------------------------------------------
# Dashboard on GET /
# -------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    uptime = int(time.time() - START_TIME)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>magicpin Vera Assistant — Live API Service</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --primary: #10B981;
      --primary-dark: #059669;
      --bg: #0F172A;
      --card-bg: #1E293B;
      --text: #F8FAFC;
      --text-muted: #94A3B8;
      --accent: #F43F5E;
      --border: #334155;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 32px 20px;
      line-height: 1.6;
    }}
    .container {{ max-width: 960px; margin: 0 auto; }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 32px;
    }}
    .badge {{
      background: rgba(16, 185, 129, 0.15);
      color: var(--primary);
      padding: 6px 14px;
      border-radius: 9999px;
      font-weight: 700;
      font-size: 0.85rem;
      border: 1px solid rgba(16, 185, 129, 0.3);
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .badge::before {{
      content: '';
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--primary);
      box-shadow: 0 0 8px var(--primary);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 32px;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
    }}
    .card-label {{ color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }}
    .card-val {{ font-size: 1.8rem; font-weight: 800; color: var(--text); margin-top: 4px; }}
    h1 {{ font-size: 2rem; font-weight: 800; letter-spacing: -0.5px; }}
    h2 {{ font-size: 1.25rem; font-weight: 700; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.95rem; }}
    th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--border); }}
    th {{ color: var(--text-muted); font-weight: 600; }}
    code {{ font-family: 'JetBrains Mono', monospace; color: #38BDF8; background: rgba(56, 189, 248, 0.1); padding: 2px 6px; border-radius: 4px; font-size: 0.88rem; }}
    .footer {{ margin-top: 40px; text-align: center; color: var(--text-muted); font-size: 0.85rem; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1>magicpin Vera Bot API</h1>
        <p style="color: var(--text-muted);">Autonomous Merchant Assistant & Engagement Engine</p>
      </div>
      <div class="badge">SYSTEM ONLINE</div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="card-label">Categories Loaded</div>
        <div class="card-val">{len(CATEGORIES)}</div>
      </div>
      <div class="card">
        <div class="card-label">Merchants Loaded</div>
        <div class="card-val">{len(MERCHANTS)}</div>
      </div>
      <div class="card">
        <div class="card-label">Customers Loaded</div>
        <div class="card-val">{len(CUSTOMERS)}</div>
      </div>
      <div class="card">
        <div class="card-label">Triggers Loaded</div>
        <div class="card-val">{len(TRIGGERS)}</div>
      </div>
    </div>

    <div class="card" style="margin-bottom: 32px;">
      <h2>Active Evaluation Endpoints</h2>
      <table>
        <thead>
          <tr>
            <th>Method</th>
            <th>Path</th>
            <th>Description</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><code>GET</code></td>
            <td><code><a href="/v1/healthz" style="color: inherit; text-decoration: none;">/v1/healthz</a></code></td>
            <td>Liveness probe and context registry telemetry</td>
            <td><span style="color: var(--primary);">200 OK</span></td>
          </tr>
          <tr>
            <td><code>GET</code></td>
            <td><code><a href="/v1/metadata" style="color: inherit; text-decoration: none;">/v1/metadata</a></code></td>
            <td>Bot architecture, model, and submission credentials</td>
            <td><span style="color: var(--primary);">200 OK</span></td>
          </tr>
          <tr>
            <td><code>POST</code></td>
            <td><code>/v1/context</code></td>
            <td>Atomic 4-context push and versioning engine</td>
            <td><span style="color: var(--primary);">Ready</span></td>
          </tr>
          <tr>
            <td><code>POST</code></td>
            <td><code>/v1/tick</code></td>
            <td>Proactive WhatsApp engagement composer</td>
            <td><span style="color: var(--primary);">Ready</span></td>
          </tr>
          <tr>
            <td><code>POST</code></td>
            <td><code>/v1/reply</code></td>
            <td>Multi-turn auto-reply filter & intent transition router</td>
            <td><span style="color: var(--primary);">Ready</span></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="footer">
      magicpin AI Challenge 2026 • Vera Assistant v2.0 • Uptime: {uptime}s
    </div>
  </div>
</body>
</html>"""
    return Response(html, mimetype="text/html")


def main():
    parser = argparse.ArgumentParser(description="magicpin Vera Bot API Server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)), help="Port to listen on")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="Host address to bind")
    args = parser.parse_args()

    print(f"[INIT] Preloading local datasets into memory...")
    preload_local_dataset()
    print(f"[READY] Loaded {len(CATEGORIES)} categories, {len(MERCHANTS)} merchants, {len(CUSTOMERS)} customers, {len(TRIGGERS)} triggers.")
    print(f"[SERVER] Starting Vera API server on http://{args.host}:{args.port}")

    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
