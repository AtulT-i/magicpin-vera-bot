# magicpin AI Challenge — Vera Merchant Assistant (Team Vera Elite)

**Product**: Autonomous WhatsApp Merchant Engagement & Growth Engine  
**Version**: 2.0.0  
**Submission Artifacts**: `bot.py`, `conversation_handlers.py`, `server.py`, `submission.jsonl`, `README.md`

---

## 1. Executive Summary & Approach

Production Vera chats with ~10,000 Indian local-commerce merchants daily over WhatsApp. However, traditional rule-based nudges suffer from **auto-reply pollution**, **intent-handoff failures**, **generic discount copy**, and **low touchpoint frequency**.

We built **Vera Elite** around a **deterministic 4-context synthesis engine** paired with an **adaptive multi-turn conversation manager**:
1. **Zero Hallucination Grounding**: Every metric, offer price, date, and clinical citation is derived strictly from `CategoryContext`, `MerchantContext`, `TriggerContext`, and `CustomerContext`.
2. **Category-Authentic Voice**: Distinct tonality tailored to 5 Indian verticals — clinical peer tone for dentists, warm practical for salons, fellow-operator for restaurants, motivational coaching for gyms, and trustworthy precision for pharmacies.
3. **Natural Hindi-English Code-Mix (`hi-en mix`)**: Automatic language adaptation for Indian merchants and customers that boosts trust and reply rates.
4. **Single-Action & Binary CTAs**: Every message ends with low-friction commitments ("Reply YES", "Reply 1 for Slot A, 2 for Slot B").

---

## 2. The 4-Context Composition Framework

```
┌─────────────────┐
│ CategoryContext │ ──► Vertical voice, offer catalogs, peer benchmarks, research digests
├─────────────────┤
│ MerchantContext │ ──► Performance (views, calls, CTR), active offers, owner name, locality
├─────────────────┤
│ TriggerContext  │ ──► The "Why Now" anchor (IPL matches, research papers, competitor, heatwave)
├─────────────────┤
│ CustomerContext │ ──► (Optional) Past visits, due recalls, appointment slots, language mix
└────────┬────────┘
         │
         ▼
 ┌───────────────┐
 │ bot.compose() │ ──► { body, cta, send_as, suppression_key, rationale }
 └───────────────┘
```

- **Merchant-Facing (`send_as: "vera"`)**: Connects external market events (e.g. Saturday IPL matches shifting dine-in -12%) or internal milestones with instant, turnkey solutions ("I already drafted your Swiggy banner + Insta story — live in 10 min. Reply YES").
- **Customer-Facing (`send_as: "merchant_on_behalf"`)**: Sent from the merchant's WhatsApp line directly to customers for preventive recalls, medication refills, and appointment confirmations.

---

## 3. Compulsion Levers Utilized

To drive merchant reply rates from ~4.6 turns up to high-retention partnerships, Vera Elite triggers proven psychological levers:
1. **Specificity & Verifiability**: Exact patient counts (`2,100-patient trial`), citations (`JIDA Oct 2026, p.14`), exact price anchors (`Dental Cleaning @ ₹299`).
2. **Loss Aversion**: Highlighting competitive threats (new competitor 1.3km away) and missed search traffic before windows close.
3. **Effort Externalization**: 100% of the cognitive work is completed beforehand ("Draft is ready — takes 2 minutes. Just reply YES").
4. **Social Proof & Peer Benchmarks**: Comparing performance to local peers (`CTR 2.1% vs peer median 3.0%`).
5. **Reciprocity & Curiosity**: The "Curious Ask" pattern asking the merchant about their top-demand service and instantly converting it into a Google showcase post.

---

## 4. Multi-Turn Architecture & Edge Cases

Implemented in `conversation_handlers.py`:
- **Auto-Reply Signature Filter**: Catches canned WhatsApp Business auto-replies ("Thank you for contacting us...", "Our team will respond shortly", repeated identical messages). Gracefully terminates or waits, preventing 2-3 wasted turns.
- **Instant Intent Routing**: When a merchant signals affirmative commitment ("Ok let's do it", "I want to join", "proceed"), the bot immediately switches to **ACTION mode** ("Done! Proceeding with your draft now...") and **never** re-qualifies with redundant questions.
- **WhatsApp Opt-Out & Hostility Compliance**: Instantly respects "stop", "spam", and "unsubscribe", exiting with zero friction.

---

## 5. HTTP API Endpoints (`server.py`)

Exposes the 5 endpoints required by the challenge specification:
| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/healthz` | Liveness check & context counts telemetry |
| `GET` | `/v1/metadata` | Team identity, version, and architecture specs |
| `POST` | `/v1/context` | Idempotent context ingestion with atomic version updates |
| `POST` | `/v1/tick` | Proactive WhatsApp engagement composer |
| `POST` | `/v1/reply` | Multi-turn auto-reply filter & intent transition router |
| `GET` | `/` | Web dashboard & live context inspector |

---

## 6. How to Run & Verify

### Start the API Server
```bash
python server.py --port 8080
```

### Run Judge Simulator
```bash
python judge_simulator.py
```

### Generate Submission JSONL
```bash
python generate_submission.py
```
Outputs `submission.jsonl` covering all 30 canonical test pairs.
