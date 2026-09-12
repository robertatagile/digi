# Open questions

Found by the generator. Release of pack version 2026.10.0 is blocked until each is answered and the answer is added as a source or an assumption.

| # | Question | Sources in conflict | Proposed default | Owner |
|---|----------|---------------------|------------------|-------|
| 1 | Is the email cut-off 14:00 or 13:30? | Deed 4.2 says 14:00. Ops manual 3.4 says 13:30 for fax and email. | 14:00 for all channels, per the deed. | Head of Ops |
| 2 | Is class B restricted to LISP accounts? | Legacy configuration restricts it. The deed is silent. | Keep the restriction as an assumption. | Head of Ops |
| 3 | Who receives interest on trust cash? | Deed 9.4 says the portfolio. Ops manual 5.4 describes a manco sweep. | Fund, per the deed. Flag the ops practice to Compliance. | Compliance |
| 4 | Does an SLA exist with any LISP that allows backdating? | No SLA document was provided. | `sla_intermediary` stays defined but unusable until an SLA is ingested. | Distribution |
| 5 | Which rounding applies to units, half-up or down? | Legacy export rounds down. The MDD does not say. | Half-up, flagged. The shadow run will show the difference. | Finance |
