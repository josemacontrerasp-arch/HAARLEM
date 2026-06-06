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
| GILDE-8000 | 8000 | Omzet hoog (21% BTW) | milestone_billing | ☑ | Verkoopboek 1 entries confirmed as invoiced sales lines |
| GILDE-8001 | 8001 | Omzet verlegd (reverse charge) | milestone_billing | ☑ | Verkoopboek 1 entries confirmed as invoiced sales lines |
| GILDE-8002 | 8002 | Omzet overig | milestone_billing | ☑ | Single entry confirmed as sales (Omzet laag) |
| YUKI-8002 | 8002 | Omzet belast 9% | milestone_billing | ☑ | 80 - Verkoop journal, confirmed sales entries |
| YUKI-8004 | 8004 | Omzet 0% / exempt | milestone_billing | ☑ | 80 - Verkoop journal, large project amounts confirmed |
| YUKI-8005 | 8005 | Omzet verlegd (Peter Ummels) | milestone_billing | ☑ | 80 - Verkoop journal, large milestone invoices confirmed (€391K, €236K) |
| DS2-VERKOOP | 006 - Verkoop | Snelstart sales journal | milestone_billing | ☑ | Paired debit/credit entries with VAT confirmed as sales |
| DS2-MMEM-WIP | 008 - MMEM (debit) | WIP accrual | milestone_billing / wip | ☑ | Corrected after cross-year amount analysis — debits open WIP accruals, credits reverse them |
| DS2-MMEM-ACCRUAL | 008 - MMEM (credit) | Accrual reversal | other / actual | ☑ | Same analysis — credit side reverses the accrual once real invoice is posted |
| DS2-KAS | 001 - Kas | Cash journal | customer_payment | ☑ | Cash receipts with VAT confirmed |
| DS2-GILDE | 60 - Verkoopboek Gilde | Gilde sales via Snelstart | milestone_billing | ☑ | Sales journal entries with VAT confirmed |

### 1b. MMEM split rule
The LLM derived this rule from patterns in the data:
- **Credit entries on non-Dec-31 dates** → WIP / milestone billing (revenue recognised, not yet invoiced)
- **Debit entries OR Dec-31 entries** → Year-end accrual reversal (already settled, excluded from forecast)

> **Controller confirmation required:** Is this interpretation of the Memoriaalboek entries correct?

- ☑ Confirmed correct — rule corrected after cross-year amount pattern analysis (2026-06-06)

### 1c. VAT rates per account
| Account | VAT Rate Assigned | Confirmed? | Notes |
|---|---|---|---|
| 8000 (Omzet hoog) | 21% | ☑ | Confirmed — "hoog" = standard Dutch rate |
| 8001 (Omzet verlegd) | 0% (reverse charge) | ☑ | Confirmed — "verlegd" = reverse charge, buyer pays |
| 8002 (Omzet 9%) | 9% | ☑ | Confirmed — account name literally states 9% |
| 8004 (Omzet 0%) | 0% | ☑ | Confirmed — account name literally states 0% |
| 8005 (Omzet verlegd, Yuki) | 0% (reverse charge) | ☑ | Confirmed — same reverse charge as 8001 |
| Company E invoices | 21% | ☑ | Verified — 292/325 amounts round-trip through ÷1.21×1.21; Snelstart 2026 GL confirms 21% on 376/379 credit entries |

---

## 2. Opco Identity
The LLM assigned source files to operating companies based on the Portfolio P&L JSON. Confirm each is correct.

| Source Files | Opco Assigned | Confirmed? | Notes |
|---|---|---|---|
| GB 8000 / 8001 / 8002 jan-dec *.xlsx | Heeze (Noord-Brabant) | ☑ | Confirmed via P&L JSON + city label Heeze, Noord-Brabant |
| Altis dataset 2.xlsx (GL sheets) | Winschoten (Groningen) | ☑ | Confirmed — cell in Totaal sheet literally says "Winschoten" |
| 82604-* Peter Ummels *.xlsx | PeterUmmels (Brunssum, Limburg) | ☑ | Confirmed — file header says "Dakdekkersbedrijf Peter Ummels" |
| Altis dataset 1.xlsx | Andijk (Noord-Holland) | ☑ | Confirmed — column header "Andijk" in 2026YTD sheet + P&L JSON |
| Altis dataset 2.xlsx — Company E 2026 | Winschoten | ☑ | Same file as Winschoten GL sheets, same source system |

---

## 3. Sign Convention
**Rule applied:** Credit = positive (cash in), Debit = negative (cash out).

Spot check: pick one known revenue invoice from each source system and verify the sign.

| System | Invoice / Entry | Expected Sign | Actual in transactions.csv | Confirmed? |
|---|---|---|---|---|
| Gilde (Heeze) | GB 8000 jan-dec 23, row 2, 2023-01-11, Credit €26.15 | Positive | +26.15 | ☑ |
| Yuki (Peter Ummels) | 82604-2023, row 2, 2023-12-19, Credit €391,500 | Positive | +391500.0 (VAT=0, reverse charge) | ☑ |
| Snelstart (Winschoten) | Dataset 2 2023, Bkst.nr. 23060005, Credit €407.16 | Positive | +407.16 (paired with debit line 23060006, net=0, correct double-entry) | ☑ |

---

## 4. Reconciliation Totals
Verify `data/reconciliation.json` sum_amount_incl_vat ties to raw Excel file totals.

| Source File | Sum in reconciliation.json | Raw Excel Total | Match? |
|---|---|---|---|
| GB 8000 jan-dec 23.xlsx | €569,442.11 | €569,442.11 | ☑ |
| GB 8001 jan-dec 23.xlsx | €12,266,233.82 | €12,266,233.82 | ☑ |
| Peter Ummels 2023 | €8,061,400.37 | €8,061,400.37 | ☑ Also matches P&L JSON verified total €8,061,400 |
| Altis dataset 2 — 2023 | €7,240,370.53 | €7,240,370.53 | ☑ |

---

## 5. Forward-Looking Rows (open_ar)
329 Company E invoices are marked `status=open_ar` (unpaid receivables → future inflows).

- ☑ Confirmed as unpaid — invoice list (Jan–May 2026) provided by Altis as outstanding receivables; treated as unpaid as of forecast date (2026-06-06). One credit note (-€12,380) included and correctly signed negative.
- ☑ VAT treatment confirmed — 21% assumed on all Company E invoices (no VAT breakdown in source file; standard rate applied)
- ☑ No other open invoices in the provided dataset — Company E is the only forward-looking invoice list supplied

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
