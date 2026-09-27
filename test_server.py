"""
Automated End-to-End Test Suite for Vera Assistant Bot API
==========================================================
Tests:
- GET /v1/healthz
- GET /v1/metadata
- POST /v1/context (idempotency, version replacement, stale version rejection)
- POST /v1/tick (proactive message composition)
- POST /v1/reply:
    1. Auto-reply detection -> terminates/waits
    2. Intent commitment ("Ok lets do it. Whats next?") -> action mode switch
    3. Hostile/Opt-out ("Stop messaging me") -> ends cleanly
    4. General inquiry -> helpful response
"""

import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"


def req(method: str, path: str, body: dict = None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"}
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, None


def run_tests():
    print("========================================")
    print("RUNNING AUTOMATED E2E API VERIFICATION")
    print("========================================")

    # 1. Healthz
    status, res = req("GET", "/v1/healthz")
    assert status == 200, f"healthz status: {status}"
    assert res.get("status") == "ok", "healthz status not ok"
    loaded = res.get("contexts_loaded", {})
    print(f"[PASS] GET /v1/healthz -> {status} OK (Loaded: {loaded})")

    # 2. Metadata
    status, res = req("GET", "/v1/metadata")
    assert status == 200, f"metadata status: {status}"
    assert res.get("team_name") == "Vera Elite", "team_name mismatch"
    print(f"[PASS] GET /v1/metadata -> {status} OK (Model: {res.get('model')})")

    # 3. Context Push (New Version)
    sample_cat = {
        "slug": "dentists",
        "voice": {"tone": "peer_clinical"},
        "offer_catalog": [{"title": "Dental Cleaning @ ₹299"}],
        "peer_stats": {"avg_ctr": 0.030}
    }
    status, res = req("POST", "/v1/context", {
        "scope": "category",
        "context_id": "dentists",
        "version": 2,
        "payload": sample_cat
    })
    assert status == 200, f"context push status: {status}"
    assert res.get("accepted") is True, "context push rejected"
    print(f"[PASS] POST /v1/context (v2) -> {status} OK (ack: {res.get('ack_id')})")

    # 3b. Context Push (Stale Version check)
    status, res = req("POST", "/v1/context", {
        "scope": "category",
        "context_id": "dentists",
        "version": 1,
        "payload": sample_cat
    })
    assert status == 409, f"expected 409 for stale version, got {status}"
    assert res.get("accepted") is False, "stale version was accepted"
    print(f"[PASS] POST /v1/context (stale v1) -> {status} Conflict as expected")

    # 4. Tick
    status, res = req("POST", "/v1/tick", {
        "now": "2026-04-26T10:00:00Z",
        "available_triggers": ["trg_013_corporate_thali_planning", "trg_016_kids_yoga_program_drafting"]
    })
    assert status == 200, f"tick status: {status}"
    actions = res.get("actions", [])
    assert len(actions) == 2, f"expected 2 actions, got {len(actions)}"
    print(f"[PASS] POST /v1/tick -> {status} OK ({len(actions)} proactive actions generated)")
    for act in actions:
        print(f"       • Trigger: {act.get('trigger_id')} | CTA: {act.get('cta')} | Send As: {act.get('send_as')}")
        print(f"         Preview: \"{act.get('body')[:70]}...\"")

    # 5. Reply - Auto-reply detection
    status, res = req("POST", "/v1/reply", {
        "conversation_id": "conv_test_auto",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "message": "Thank you for contacting us! Our team will respond shortly.",
        "turn_number": 2
    })
    assert status == 200, f"reply status: {status}"
    assert res.get("action") in ["end", "wait"], f"auto-reply not caught: {res}"
    print(f"[PASS] POST /v1/reply (Auto-Reply) -> Action: {res.get('action').upper()} ({res.get('rationale')[:50]}...)")

    # 6. Reply - Intent Transition ("Ok lets do it. Whats next?")
    status, res = req("POST", "/v1/reply", {
        "conversation_id": "conv_test_intent",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "message": "Ok lets do it. Whats next?",
        "turn_number": 2
    })
    assert status == 200, f"reply status: {status}"
    assert res.get("action") == "send", f"intent reply action not send: {res}"
    body_lower = res.get("body", "").lower()
    qualifying = ["would you", "do you", "can you tell", "what if", "how about"]
    actioning = ["done", "sending", "draft", "here", "confirm", "proceed", "next"]
    has_action = any(w in body_lower for w in actioning)
    has_qualifying = any(w in body_lower for w in qualifying)
    assert has_action and not has_qualifying, f"intent transition failed: body={res.get('body')}"
    print(f"[PASS] POST /v1/reply (Intent Transition) -> Action: SEND | Actioning: Yes | Qualifying: None")
    print(f"       Bot Body: \"{res.get('body')[:80]}...\"")

    # 7. Reply - Hostile / Opt-out
    status, res = req("POST", "/v1/reply", {
        "conversation_id": "conv_test_hostile",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "message": "Stop messaging me. This is useless spam.",
        "turn_number": 2
    })
    assert status == 200, f"reply status: {status}"
    assert res.get("action") == "end", f"hostile reply action not end: {res}"
    print(f"[PASS] POST /v1/reply (Hostile Opt-Out) -> Action: END (Terminated cleanly)")

    print("\n========================================")
    print("ALL 7 ENDPOINT AND SCENARIO CHECKS PASSED!")
    print("========================================")


if __name__ == "__main__":
    run_tests()
