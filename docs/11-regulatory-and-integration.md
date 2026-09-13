# 11. Regulatory context and integration

This is the short map. **Doc 13** models legislation as a controlled, manco-managed layer with obligations, bindings, coverage and a compliance calendar.

Numeric limits and rates below are **pack parameters**. They change. Every pack rule cites its source and its effective date. Check current legislation before release.

## Regulatory map

| Regime | What it affects | Kernel | Pack |
|--------|-----------------|--------|------|
| **CISCA** and its notices | Manco duties, deed, trustee, forward pricing, segregated trust money, ring-fencing, pricing error handling | Forward pricing, immutability, control accounts, price versions | Deed-specific rules, ring-fencing thresholds, materiality |
| **ASISA standards** | Pricing errors, fund classification, cost disclosure, MDD content | Correction block mechanics | Materiality, disclosure templates |
| **FSR Act** conduct standards, complaints and returns; **COFI** incoming | Treating customers fairly, complaints, conduct reporting | Audit trail, as-at reproducibility | Communications, complaint workflows |
| **FAIS** | Advisers and FSPs, LISP as administrative FSP | Adviser party type, mandate flags | Adviser fee rules, mandate checks |
| **FICA** | Customer due diligence, risk rating, threshold and suspicious transaction reports | KYC status flag, dealing gates, large transaction flags | Risk rating rules, document lists, report formats |
| **POPIA** | Personal information | Tenant isolation, access logging, retention hooks | Retention periods, consent handling |
| **Income Tax Act** | IT3(b), IT3(c), IT3(s), dividends tax, interest withholding, VAT on fees, tax directives | Tax lots, withholding postings, `TAX_WITHHELD_PAYABLE` | Rates, methods, certificate formats |
| **Pension Funds Act** | Regulation 28, two-pot components, section 14 transfers, retirement rules | Components, restriction flags, transfer block | Limits, ages, per-product rules |
| **Payments regulation** | Debit orders, DebiCheck, beneficiary verification | Payment pipeline, verification gates | Bank formats, retry rules |

## Integration map

| System | Direction | What flows | Adapter contract |
|--------|-----------|------------|------------------|
| **FinSwitch** | Both | LISP instructions, confirmations, prices, statements | Instruction in, confirmation in, bulk instruction out |
| **Banks** | Both | Statements, intraday feeds, collections, payments, returns | Bank line in, payment out, confirmation in |
| **Fund accounting** | In | Official and indicative prices, units in issue for reconciliation | `PublishPrice`, reconciliation feed |
| **Trustee or custodian** | Both | Settlement, reports, approvals | Read-only as-at views, settlement confirmations |
| **SARS** | Out and in | IT3 submissions, dividends tax, tax directives | Certificate files, directive request and response |
| **FIC** | Out | Threshold and suspicious transaction reports | Report files |
| **FSCA** | Out | Conduct and statutory returns | Report files |
| **Adviser and investor portals** | Both | Instructions, values, documents | Commands and as-at queries |
| **CRM and document management** | Both | Parties, evidence, correspondence | Evidence references on commands |
| **Data warehouse** | Out | Events and projections with as-at tags | Event stream |

Adapters translate formats. They never decide. A pack owns the mapping. The kernel owns the command.

## Security and tenancy

- Tenant isolation at the data layer. No shared tables across tenants.
- Role-based access with segregation of duties enforced by the kernel.
- Every read of investor data is logged.
- Data residency in South Africa.
- Packs run in a sandbox with no network. Generated code cannot exfiltrate.
- Model calls during generation use tenant documents under the tenant's data agreement. Nothing crosses tenants.
