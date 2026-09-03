# Dataset Acquisition Plan — Legal Memory Layer

**Date:** 2026-08-13 · **Status:** all sources below verified reachable from this machine today
**Serves:** `MEMORY_LAYER_IMPLEMENTATION_PLAN_2026-08-13.md` Phase 2 (legal adapter pilot gold), Phase 4 (benchmark), Memory Gym synthesizer corpus
**Number discipline:** sizes are as-published on the source pages; verify before quoting.

---

## 1. The standout: KanoonGPT/indian-case-laws (download today)

**HF:** `huggingface.co/datasets/KanoonGPT/indian-case-laws` · **17.1M rows** · year-partitioned structured parquet, 1950–2026 · **schema is a ready-made longitudinal substrate**:

| Field | Use in our system |
|---|---|
| `party_petitioner` / `party_respondent` / `party_caption` | party entity resolution (§4.2) |
| `docket_number`, `cnr_number`, `neutral_citation`, `law_report_citation` | deterministic identity keys (Tier 1) |
| `court_name` (26 values), `bench_name`, `presiding_judge`, `coram_members` | court/judge taxonomy seeds |
| `decision_date`, `registration_date`, `disposition_text` (568 values) | temporal axis + holding/outcome ground truth |
| `indexable_text`, `headnote_text` | extraction corpus (full text also on S3) |
| `source_json_s3_url`, `source_pdf_s3_url` | full judgment JSON + PDF from public S3 (`indian-high-court-judgments.s3.ap-south-1.amazonaws.com`) |
| `quality_json.completeness` flags (`has_data_mismatch`, `has_decision_before_registration`, `has_errors`…) | **pre-computed data-quality filtering — free gold-dataset hygiene** |

**Download (selective, year-partitioned):**
```bash
# base URL pattern for structured parquets:
# https://huggingface.co/datasets/KanoonGPT/indian-case-laws/resolve/main/structured/v1/year=2024/indian_case_laws_structured_v1_year=2024.parquet
# grab the auto-converted parquet list for the full set:
curl -s "https://huggingface.co/api/datasets/KanoonGPT/indian-case-laws/parquet" | jq -r '.default.train[]'
# 78 shards for the full 17.1M rows; year partitions for surgical downloads
```
License: check the dataset card before commercial use (open, but verify).

**Why it changes the plan:** the pilot gold does not need to be built from raw PDFs. Start with 3–5 multi-year cases *from this dataset* (same docket across appeals/remands — selectable via `cnr_number` groups), build gold frames in a day, and keep CourtListener as the US counterpart.

## 2. India (all verified reachable)

| Source | What | How |
|---|---|---|
| **AWS Open Data: Indian Supreme Court Judgments** | SC judgment PDFs/JSON/parquet/tar, no AWS account needed | `aws s3 ls --no-sign-request s3://indian-supreme-court-judgments/` (verified: `data/`, `metadata/` prefixes) |
| **vihaannnn/Indian-Supreme-Court-Judgements-Chunked** (HF) | 21K SC judgments, pre-chunked + embedded | `huggingface-cli download vihaannnn/Indian-Supreme-Court-Judgements-Chunked` |
| **ILDC** (Legal-NLP-EkStep) | Annotated Indian judgment tasks (summarization, court/task prediction) | github.com/Legal-NLP-EkStep/ILDC |
| **OpenNyAI** | Judgment QA/summarization/translation annotations | opennyai.org/datasets |
| **openjustice-in/ecourts** | Python scraper for Indian court orders | github.com/openjustice-in/ecourts |
| **vanga scrapers** | SC + High Court judgment scrapers | github.com/vanga/indian-supreme-court-judgments, /indian-high-court-judgments |
| **DDL Judicial Data Portal** | devdatalab.org judicial data (India) | devdatalab.org/judicial-data |

## 3. US

| Source | What | How |
|---|---|---|
| **CourtListener bulk data** (Free Law Project) | 9M+ opinions; bulk exports | wiki.free.law/c/courtlistener/help/api/bulk-data/bulk-legal-data — bulk dumps for members; full API now in membership tiers (free.law/2026/05/07) |
| **Harvard case.law** | 6.5M-opinion CAP corpus | migrated to CourtListener; bulk data via case.law |
| **Apify CourtListener scraper** | scraping alternative | apify.com/jungle_synthesizer/courtlistener-opinion-scraper |
| **CaseHOLD / CUAD / LegalBench** (HF) | Benchmarks: holding-MCQ, contract span-extraction, component evals | `huggingface-cli download nguha/legalbench allenai/casehold`; CUAD via atticudprojectai.org |

## 4. UK & multilingual (longitudinal precedent, cleanest text)

| Source | What | How |
|---|---|---|
| **UK National Archives Find Case Law API** | Free JSON judgments, clean metadata, multi-year procedural histories | nationalarchives.github.io/ds-find-caselaw-docs/public |
| **OpenCaseLaw (CH)** | **950K+ Swiss decisions with citation graph**; bulk Parquet on HF | `huggingface-cli download voilaj/swiss-caselaw` — citation graph = ready-made precedent-track gold |
| **MultiLegalPile** (HF joelito/legal-pile) | 24-language legal corpus | `huggingface-cli download joelito/legal-pile` |
| **Open Australian Legal Corpus** (HF umarbutler/…) | Legislative + judicial documents | HF download |

## 5. How each dataset maps to the build plan

| Plan phase | Dataset |
|---|---|
| Phase 2 pilot gold (India corpus) | KanoonGPT year partitions → 3–5 multi-year `cnr_number` case chains; gold frames in the existing curation format |
| Phase 2 pilot gold (US) | CourtListener (membership) → 3 multi-year federal cases |
| Phase 2 schema/taxonomy seeds | KanoonGPT `disposition_text` (568 values), `court_name` (26), quality flags |
| Phase 4 benchmark | KanoonGPT (filtered by quality flags) as the public track-linking corpus + existing frozen_30 as task #1 |
| Memory Gym synthesizer domain language | `extraction/finding_type_taxonomy.py` + legal taxonomy induced from KanoonGPT headnotes/dispositions |
| Precedent tracks (cross-case linking) | OpenCaseLaw citation graph; UK case law cited-by data |
| Benchmarks (membership checks) | LegalBench, CaseHOLD, CUAD |

## 6. Licensing notes (GATE 0 due-diligence inputs)

- CourtListener: non-profit, membership-tiered API; bulk data terms per free.law — read before commercial use.
- Indian Kanoon-style scrapes: ToS-restricted; the KanoonGPT/AWS-datasets route avoids scraping entirely — prefer it.
- UK Find Case Law: explicitly free re-use terms.
- OpenCaseLaw: Parquet on HF, verify license field.
- HF datasets: verify each card's license before shipping anything derived.

## 7. Immediate actions

1. `aws s3 ls --no-sign-request s3://indian-supreme-court-judgments/data/parquet/` → confirm partition layout, pull one year.
2. Download 3–4 KanoonGPT year parquets (e.g., 2019–2024) → build the 3-case pilot gold.
3. Confirm KanoonGPT license + CourtListener membership tier for US gold.
4. Store raw datasets under `~/data/legal/` (outside the repo); curated gold goes to `evaluation/frame_annotations/legal_gold_v1/`.

---

## 8. VERIFIED ON TYRONE (2026-08-14)

Downloads live at `tyrone:~/data/legal/`:

| Asset | Status | Size |
|---|---|---|
| KanoonGPT 2015–2025 year parquets | **downloaded, analyzed** | 7.8GB, 13.1M rows |
| AWS SC metadata parquets 1950–2026 | **downloaded, analyzed** | 47MB, 43,532 rows |

### Verified schema & quality findings

- **KanoonGPT (HC+SC)**: 39 columns; `cnr_number` coverage 100%; quality flags ≥94% clean on every dimension (`has_errors` 0.0%, `error_count>0` 0.0%, `has_data_mismatch` 0.0%); `review_priority`: 72.2% low / 24.3% medium / 3.4% high; **8.84% `has_source_missing`** — filter out. **`indexable_text` is a ~426-char header summary only — full text is NOT in the parquet.**
- **Courts**: HC-dominated (Allahabad 1.6M, Madras 1.4M, P&H 1.26M, Patna 1.1M…); SC subset 8,758 rows in KG.
- **Dispositions**: 568 values; top: DISMISSED 1.69M, DISPOSED OF 1.39M, ALLOWED 1.35M — usable outcome taxonomy.
- **Neutral citations**: essentially absent in KG (0.07%); present in **SC-AWS metadata** (`case_id` = "2024 INSC 735", `citation` = "[2024] 10 S.C.R. 108").
- **Chain analysis**: `cnr_number` chains are duplicate orders (0.1%), NOT appeals. Multi-decision **party-caption** chains: 749,711 captions, 3.41M rows (26%). The real longitudinal keys: **docket_number + neutral citation** (party pair is a search hint, NEVER an identity key — Darshan Singh name-collision trap, `PILOT_DATA_FINDINGS_2026-08-14.md` §1.2; corrected 2026-08-14).

### Full-text retrieval (verified working)

- **SC**: `https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/data/pdf/year={Y}/english/{path}_EN.pdf` — `path` field from the SC metadata parquet maps 1:1 (100% coverage). Born-digital, clean text: verified 18-page judgment extracting perfectly with pypdf (neutral citation, docket, coram, headnotes all in the PDF).
- **HC**: JSONs on S3 contain header HTML only (~500 chars); full text via PDFs at `pdf_link` in the JSON (born-digital, ~70KB typical). Test fetch failed only when using a wrong path; correct paths from dataset rows resolve.

### Pilot-gold selection (SC case families, verified)

43,532 SC cases, 1950–2026. **188 case families** = same petitioner+respondent across ≥2 decision-years. Candidates:

| Family | Years | Decisions |
|---|---|---|
| M.C. Mehta v. Union of India (env. PIL) | 1991–2009 | 21 |
| Darshan Singh v. State of Punjab | 1952–2024 | 6 |
| Common Cause v. Union of India | 1996–2017 | 4 |
| T.N. Godavarman v. Union of India | 2008–2025 | 4 |

**Pilot gold = 3 families × all their PDFs** (downloadable today): gold frames for procedural events / issues / holdings / citations per decision; tracks link decisions across decades. This is the legal analog of the 8-patient dev cohort — small, deep, verifiable.

