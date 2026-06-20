# Decision-curve analysis — net benefit (diabetes, MIMIC-IV test set)

| Threshold | Treat-all | Concurrent model | Pre-onset model |
|---|---|---|---|
| 0.10 | -0.0119 | 0.0393 | 0.0231 |
| 0.20 | -0.1384 | 0.0296 | 0.0080 |
| 0.30 | -0.3011 | 0.0228 | 0.0033 |

*Net benefit > treat-all and > 0 across the clinically relevant threshold range means flagging patients by the model is preferable to treating everyone or no one. The pre-onset model retains positive net benefit, i.e. clinical utility survives the removal of leaky concurrent features.*