---
as_of: '2026-11-01'
author_agent: analyst
created_at: '2026-11-02T00:15:31.043005+00:00'
expires_at: '2026-11-03T00:15:31.043014+00:00'
generation_options:
  num_ctx: 16384
  seed: 42
  temperature: 0
id: c9ce95ad095040fd
input_data_hash: b0c2b4aa9270a188c13a672ee88078ad2282e990a2d7a0f5a41e4331d4e38da0
model_digest: mock-sha256-v1
model_name: llama3.1:8b
parents: {}
prompt_versions:
  analyst: 21987984ce9290f64a444777179c57df2fee03cffc43e9f06b9db6b202e23ed3
requested_action:
  action: publish_research
ticker: DEMO
status: in_review
content_hash: 7e6687d9c7eb3bf86475e8ef7cd6fd83eb5d4b4571ca87f741db0e4f786b7810
approval_hash: null
approver: null
override_reason: null
---

# Equity research

Revenue is 1e+09 USD currency (source: Synthetic educational fixture - not a real security; as-of 2026-11-01). Cash generation depends on the explicit margin assumption 0.12 (source: agent forecast assumption, not observed data; input as-of 2026-11-01). This is a synthetic demonstration, with uncertain forecasts.

## Input provenance

Metric | Value | Unit | Currency | Source | As-of
--- | ---: | --- | --- | --- | ---
revenue | 1000000000 | currency | USD | Synthetic educational fixture - not a real security | 2026-11-01
fcff | 100000000 | currency | USD | Synthetic educational fixture - not a real security | 2026-11-01
cash | 150000000 | currency | USD | Synthetic educational fixture - not a real security | 2026-11-01
debt | 200000000 | currency | USD | Synthetic educational fixture - not a real security | 2026-11-01
shares | 10000000 | shares | USD | Synthetic educational fixture - not a real security | 2026-11-01
price | 100 | per_share | USD | Synthetic educational fixture - not a real security | 2026-11-01

## Forecast assumptions

These are hypothetical agent assumptions, not fetched facts.

- wacc: 0.1 (source: analyst assumption; input as-of 2026-11-01)
- growth: 0.05 (source: analyst assumption; input as-of 2026-11-01)
- terminal_growth: 0.02 (source: analyst assumption; input as-of 2026-11-01)
- fcff_margin: 0.12 (source: analyst assumption; input as-of 2026-11-01)
- years: 5 (source: analyst assumption; input as-of 2026-11-01)

## Deterministic DCF

- enterprise_value: 1735454267.980329 (source: Python DCF over inputs above; input as-of 2026-11-01)
- equity_value: 1685454267.980329 (source: Python DCF over inputs above; input as-of 2026-11-01)
- fair_value: 168.5454267980329 (source: Python DCF over inputs above; input as-of 2026-11-01)
- terminal_share: 0.6986526755774511 (source: Python DCF over inputs above; input as-of 2026-11-01)
- pv_flows: 522974500.31356525 (source: Python DCF over inputs above; input as-of 2026-11-01)
- pv_terminal: 1212479767.6667638 (source: Python DCF over inputs above; input as-of 2026-11-01)
- observed_fcff_margin: 0.1 (source: Python DCF over inputs above; input as-of 2026-11-01)
- warnings: [] (source: Python DCF over inputs above; input as-of 2026-11-01)

---
Research and education tool only; not financial advice. Paper trading only.
