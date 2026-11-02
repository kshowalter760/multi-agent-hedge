---
as_of: '2026-11-01'
author_agent: pm
created_at: '2026-11-02T00:22:58.803375+00:00'
expires_at: '2026-11-03T00:22:58.803382+00:00'
generation_options:
  num_ctx: 16384
  seed: 42
  temperature: 0
id: 8546316fe3fa47d7
input_data_hash: b0c2b4aa9270a188c13a672ee88078ad2282e990a2d7a0f5a41e4331d4e38da0
model_digest: mock-sha256-v1
model_name: llama3.1:8b
parents:
  89f746ec578c43ea: a84f4c7c3c4befe607c3e563623ccab7e7609ddfc9ae97ef7947212a20248859
prompt_versions:
  pm: 85b06a17f1a85be50a7625999f1f9e96673c09865440c161ce4f84df7e9e6766
requested_action:
  action: buy
  limit_price: 100.0
  trade:
    action: buy
    currency: USD
    limit_price: 100.0
    price: 100.0
    sector: Industrials
    shares: 50
    ticker: DEMO
  weight: 0.05
ticker: DEMO
status: in_review
content_hash: 9417ad169ec6ad7667f4b9c5049a1107eff8d3f63f29a32d9f5895f102c3e0d8
approval_hash: null
approver: null
override_reason: null
---

# Portfolio proposal

Propose a limited paper allocation subject to cash and sector caps.

Paper order (source: PM assumptions and deterministic sizing; input as-of 2026-11-01).

```json
{
  "action": "buy",
  "weight": 0.05,
  "limit_price": 100.0,
  "trade": {
    "action": "buy",
    "shares": 50,
    "price": 100.0,
    "limit_price": 100.0,
    "ticker": "DEMO",
    "sector": "Industrials",
    "currency": "USD"
  }
}
```

---
Research and education tool only; not financial advice. Paper trading only.
