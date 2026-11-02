---
as_of: '2026-11-01'
author_agent: risk
created_at: '2026-11-02T00:22:51.723601+00:00'
expires_at: '2026-11-03T00:22:51.723610+00:00'
generation_options:
  num_ctx: 16384
  seed: 42
  temperature: 0
id: 89f746ec578c43ea
input_data_hash: b0c2b4aa9270a188c13a672ee88078ad2282e990a2d7a0f5a41e4331d4e38da0
model_digest: mock-sha256-v1
model_name: qwen2.5:7b
parents:
  c9ce95ad095040fd: 7e6687d9c7eb3bf86475e8ef7cd6fd83eb5d4b4571ca87f741db0e4f786b7810
prompt_versions:
  risk: d0a060b550c8c8e50c276e5ceb67610db12786fed74a1e16614dbd1eff888ad0
requested_action:
  verdict: approve
ticker: DEMO
status: in_review
content_hash: a84f4c7c3c4befe607c3e563623ccab7e7609ddfc9ae97ef7947212a20248859
approval_hash: null
approver: null
override_reason: null
---

# Adversarial risk review

Independent arithmetic reconciles. Terminal dependence and margin compression remain material risks. The base valuation is 168.545 (source: deterministic DCF using cited inputs and assumptions; input as-of 2026-11-01).

Independent recomputation, sensitivity grid and scenarios. Source: Python risk engine; input as-of 2026-11-01. Scenario parameters are stress assumptions.

```json
{
  "recomputed": {
    "enterprise_value": 1735454267.9803288,
    "equity_value": 1685454267.9803288,
    "fair_value": 168.54542679803288,
    "terminal_share": 0.6986526755774511,
    "pv_flows": 522974500.3135652,
    "pv_terminal": 1212479767.6667635,
    "observed_fcff_margin": 0.1
  },
  "sensitivity": [
    {
      "wacc": 0.08,
      "terminal_growth": 0.01,
      "fair_value": 200.57598879743938
    },
    {
      "wacc": 0.08,
      "terminal_growth": 0.02,
      "fair_value": 227.37899019775944
    },
    {
      "wacc": 0.08,
      "terminal_growth": 0.03,
      "fair_value": 264.9031921582075
    },
    {
      "wacc": 0.1,
      "terminal_growth": 0.01,
      "fair_value": 154.01680213100195
    },
    {
      "wacc": 0.1,
      "terminal_growth": 0.02,
      "fair_value": 168.5454267980329
    },
    {
      "wacc": 0.1,
      "terminal_growth": 0.03,
      "fair_value": 187.2250870842155
    },
    {
      "wacc": 0.12000000000000001,
      "terminal_growth": 0.01,
      "fair_value": 124.43792169744316
    },
    {
      "wacc": 0.12000000000000001,
      "terminal_growth": 0.02,
      "fair_value": 133.2862854003906
    },
    {
      "wacc": 0.12000000000000001,
      "terminal_growth": 0.03,
      "fair_value": 144.10095214843747
    }
  ],
  "scenarios": {
    "bear": {
      "assumptions": {
        "wacc": 0.12000000000000001,
        "growth": 0.020000000000000004,
        "terminal_growth": 0.02,
        "fcff_margin": 0.096,
        "years": 5
      },
      "result": {
        "enterprise_value": 979199999.9999998,
        "equity_value": 929199999.9999998,
        "fair_value": 92.91999999999997,
        "terminal_share": 0.6264850986190417,
        "pv_flows": 365745791.4322343,
        "pv_terminal": 613454208.5677655,
        "observed_fcff_margin": 0.1,
        "warnings": []
      }
    },
    "base": {
      "assumptions": {
        "wacc": 0.1,
        "growth": 0.05,
        "terminal_growth": 0.02,
        "fcff_margin": 0.12,
        "years": 5
      },
      "result": {
        "enterprise_value": 1735454267.980329,
        "equity_value": 1685454267.980329,
        "fair_value": 168.5454267980329,
        "terminal_share": 0.6986526755774511,
        "pv_flows": 522974500.31356525,
        "pv_terminal": 1212479767.6667638,
        "observed_fcff_margin": 0.1,
        "warnings": []
      }
    },
    "bull": {
      "assumptions": {
        "wacc": 0.09000000000000001,
        "growth": 0.08,
        "terminal_growth": 0.02,
        "fcff_margin": 0.144,
        "years": 5
      },
      "result": {
        "enterprise_value": 2704208260.96521,
        "equity_value": 2654208260.96521,
        "fair_value": 265.420826096521,
        "terminal_share": 0.7409873202511004,
        "pv_flows": 700424228.2717106,
        "pv_terminal": 2003784032.693499,
        "observed_fcff_margin": 0.1,
        "warnings": []
      }
    }
  }
}
```

---
Research and education tool only; not financial advice. Paper trading only.
