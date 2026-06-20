# Decision-curve analysis — net benefit (heart failure (identification), MIMIC-IV test set)

| Threshold | Treat-all | Full CDW model (30 features) | Guideline risk factors + eGFR |
|---|---|---|---|
| 0.10 | 0.0529 | 0.1087 | 0.0994 |
| 0.20 | -0.0655 | 0.0840 | 0.0662 |
| 0.30 | -0.2177 | 0.0648 | 0.0422 |

*Net benefit > treat-all and > 0 across the clinically relevant threshold range means flagging patients by the model is preferable to treating everyone or no one. The pre-onset model retains positive net benefit, i.e. clinical utility survives the removal of leaky concurrent features.*