# Decision-curve analysis — net benefit (chronic kidney disease, MIMIC-IV test set)

| Threshold | Treat-all | Concurrent model | Pre-onset model |
|---|---|---|---|
| 0.10 | 0.0309 | 0.0734 | 0.0760 |
| 0.20 | -0.0902 | 0.0556 | 0.0453 |
| 0.30 | -0.2460 | 0.0404 | 0.0245 |

*Net benefit > treat-all and > 0 across the clinically relevant threshold range means flagging patients by the model is preferable to treating everyone or no one. The pre-onset model retains positive net benefit, i.e. clinical utility survives the removal of leaky concurrent features.*