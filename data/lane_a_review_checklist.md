# Lane A — Data Review Checklist
**Reviewer:** ___________________  
**Date:** ___________________  
**Purpose:** Confirm that all LLM-assisted data decisions are auditable and controller-approved before the forecast is presented.

---

## 1. GL Mapping (`data/gl_mapping.csv`)

### 1a. Account → Driver classification
For each mapping rule, confirm the `driver_type` is correct.

| Rule ID | Native Account | Description | Driver Assigned | Confirmed? | Notes |
|---|---|---|---|---|---|
| GILDE-8000 | 8000 | Omzet hoog (21% BTW) | milestone_billing | ☐ | |
| GILDE-8001 | 8001 | Omzet verlegd (reverse charge) | milestone_billing | ☐ | |
| GILDE-8002 | 8002 | Omzet overig | milestone_billing | ☐ | |
| YUKI-8002 | 8002 | Omzet belast 9% | milestone_billing | ☐ | |
| YUKI-8004 | 8004 | Omzet 0% / exempt | milestone_billing | ☐ | |
| YUKI-8005 | 8005 | Omzet verlegd (Peter Ummels) | milestone_billing | ☐ | |
| DS2-VERKOOP | 006 - Verkoop | Snelstart sales journal | milestone_billing | ☐ | |
| DS2-MMEM-WIP | 008 - MMEM (credit, mid-period) | WIP recognition | milestone_billing | ☐ | |
| DS2-MMEM-ACCRUAL | 008 - MMEM (debit or Dec-31) | Year-end accrual reversal | other | ☐ | |
| DS2-KAS | 001 - Kas | Cash journal | customer_payment | ☐ | |
| DS2-GILDE | 60 - Verkoopboek Gilde | Gilde sales via Snelstart | milestone_billing | ☐ | |

### 1b. MMEM split rule
The LLM derived this rule from patterns in the data:
- **Credit entries on non-Dec-31 dates** → WIP / milestone billing (revenue recognised, not yet invoiced)
- **Debit entries OR Dec-31 entries** → Year-end accrual reversal (already settled, excluded from forecast)

> **Controller confirmation required:** Is this interpretation of the Memoriaalboek entries correct?

- ☐ Confirmed correct  
- ☐ Needs correction — notes: ___________________

### 1c. VAT rates per account
| Account | VAT Rate Assigned | Confirmed? | Notes |
|---|---|---|---|
| 8000 (Omzet hoog) | 21% | ☐ | |
| 8001 (Omzet verlegd) | 0% (reverse charge) | ☐ | |
| 8002 (Omzet 9%) | 9% | ☐ | |
| 8004 (Omzet 0%) | 0% | ☐ | |
| 8005 (Omzet verlegd, Yuki) | 0% (reverse charge) | ☐ | |
| Company E invoices | 21% (assumed, no breakdown) | ☐ | |

---

## 2. Opco Identity
The LLM assigned source files to operating companies based on the Portfolio P&L JSON. Confirm each is correct.

| Source Files | Opco Assigned | Confirmed? | Notes |
|---|---|---|---|
| GB 8000 / 8001 / 8002 jan-dec *.xlsx | Heeze (Noord-Brabant) | ☐ | |
| Altis dataset 2.xlsx (GL sheets) | Winschoten (Groningen) | ☐ | |
| 82604-* Peter Ummels *.xlsx | PeterUmmels (Brunssum, Limburg) | ☐ | |
| Altis dataset 1.xlsx | Andijk (Noord-Holland) | ☐ | |
| Altis dataset 2.xlsx — Company E 2026 | Winschoten | ☐ | |

---

## 3. Sign Convention
**Rule applied:** Credit = positive (cash in), Debit = negative (cash out).

Spot check: pick one known revenue invoice from each source system and verify the sign.

| System | Invoice / Entry | Expected Sign | Actual in transactions.csv | Confirmed? |
|---|---|---|---|---|
| Gilde (Heeze) | _________________ | Positive | _________________ | ☐ |
| Yuki (Peter Ummels) | _________________ | Positive | _________________ | ☐ |
| Snelstart (Winschoten) | _________________ | Positive | _________________ | ☐ |

---

## 4. Reconciliation Totals
Verify `data/reconciliation.json` sum_amount_incl_vat ties to raw Excel file totals.

| Source File | Sum in reconciliation.json | Raw Excel Total | Match? |
|---|---|---|---|
| GB 8000 jan-dec 23.xlsx | €569,442 | _________________ | ☐ |
| GB 8001 jan-dec 23.xlsx | €12,266,234 | _________________ | ☐ |
| Peter Ummels 2023 | €8,061,400 | _________________ | ☐ |
| Altis dataset 2 — 2023 | €7,240,371 | _________________ | ☐ |

---

## 5. Forward-Looking Rows (open_ar)
329 Company E invoices are marked `status=open_ar` (unpaid receivables → future inflows).

- ☐ Confirmed these are genuinely unpaid as of the forecast date
- ☐ VAT treatment confirmed (21% assumed on all — correct?)
- ☐ No other open invoices are missing from the dataset

---

## 6. Overall Sign-off

| Item | Approved? | Approver | Date |
|---|---|---|---|
| GL mapping rules | ☐ | | |
| MMEM split rule | ☐ | | |
| VAT rates | ☐ | | |
| Opco assignments | ☐ | | |
| Sign convention | ☐ | | |
| Reconciliation totals | ☐ | | |
| open_ar rows | ☐ | | |

**Summary note (required for submission):**
> ___________________________________________________________________________________
> ___________________________________________________________________________________

---

*This checklist was generated as part of the LLM-assisted GL mapping process. Per the hackathon rules, all LLM suggestions must be reviewable and auditable by a controller. This document is the evidence of that review.*
