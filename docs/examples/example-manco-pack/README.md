# Example Manco Pack

A **generated Tenant Pack** for a fictional manco, "Example Manco". It shows the shape of the output the generation pipeline produces. Every value here is invented.

| File | Contents |
|------|----------|
| `pack.yaml` | Pack metadata, funds, classes, calendars, fees, distributions, ring-fencing. |
| `policies.yaml` | Units-on policy, backdating and loss allocation, pricing errors, approval tiers. |
| `workflows/investment.yaml` | Investment state machine. |
| `workflows/redemption.yaml` | Redemption state machine with holds and approval tiers. |
| `tests/redemption.scenarios.yaml` | Scenario tests with expected postings. |
| `tests/backdating.scenarios.yaml` | Scenario tests for the delta and the loss owner. |
| `regulatory/obligations.yaml` | The manco-managed obligation register: FSR Act, COFI, FAIS, CISCA, FICA, POPIA and tax obligations bound to kernel controls, pack rules or attested procedures. |
| `regulatory/compliance-calendar.yaml` | Statutory returns and attestations with owners. Overdue is a break. |
| `open-questions.md` | Ambiguities the generator found. Release is blocked until they are answered. |

Every rule carries a `source`. A rule without one carries an `assumption` with an owner.

Every workflow and policy carries `serves:`, naming the obligations it meets. The coverage gate refuses release while an applicable in-force obligation has no binding.
