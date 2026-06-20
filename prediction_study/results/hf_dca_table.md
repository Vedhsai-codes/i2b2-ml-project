# Decision-curve analysis — net benefit (HF, MIMIC-IV test set)

| Threshold | Treat-all | Concurrent model | Pre-onset model |
|---|---|---|---|
| 0.10 | 0.0468 | 0.0982 | 0.0840 |
| 0.20 | -0.0723 | 0.0710 | 0.0454 |
| 0.30 | -0.2255 | 0.0492 | 0.0233 |

*Net benefit > treat-all and > 0 across the clinically relevant threshold range means flagging patients by the model is preferable to treating everyone or no one. The pre-onset model retains positive net benefit, i.e. clinical utility survives the removal of leaky concurrent features.*