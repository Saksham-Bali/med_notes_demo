# pre

This is IndigoEdge's monorepo. It holds one live product, the strategy behind it, and the
earlier work that product replaced.

## What is live

- **`findingframe/`** — the product. An audit-grade oncology radiology pipeline: an LLM pulls
  structured "frames" (finding type, anatomy, laterality, measurement, temporal change,
  assertion) out of each report, each tied to a verbatim source sentence; deterministic code
  links frames into longitudinal tracks and computes RECIST 1.1 progression; a clinician
  reviews and signs off on every track; every fact and every sign-off is hash-chained and
  independently re-verifiable. Sold to market as **Dasyante**. Backend (FastAPI), worker, and
  web app (Next.js) are deployed and healthy — see `findingframe/HANDOFF.md` for current status
  and `findingframe/README.md` for the quickstart. It productionizes the FindingFrame research
  engine kept at `tmc/` (below).
- **`strategy/`** — the positioning: `PITCH.md`, `MARKET_RESEARCH.md`, `PRODUCT_AND_MARKET.md`,
  `PRODUCT_BUILD_PLAN.md`. Read these for why the product is shaped the way it is, and for the
  India-first, pharma/CRO-revenue plan.

## What is archived, and why

**`archive/cliniq-era/`** holds a full earlier platform: a 10-agent pipeline named ClinIQ,
covering voice intake (Sarvam), TTS/translation, general OCR, department-merge,
discharge-summary generation, counselling/SOAP extraction, a multi-tenant onboarding flow, SSO,
and DICOM/EHR integration. `strategy/PRODUCT_BUILD_PLAN.md` states the scope decision plainly:
the current build "builds the product defined by `strategy/`... **not** the old `pre/` 'ClinIQ'
10-agent platform." That earlier platform is parked, not deleted — its code and history are
moved, not removed, in case any part of it is worth mining later.

Nothing in `findingframe/` or `strategy/` depends on the archived material.

## Repos nested inside this one

Three directories here are their own git repositories, each with its own remote. This repo
ignores them (see `.gitignore`) rather than tracking them as submodules — there is no
`.gitmodules` file and no gitlinks, they are just separate checkouts that happen to live under
this directory:

- **`tmc/`** — the FindingFrame research engine (remote: `med-notes.git`). `findingframe/`
  vendors and adapts this engine; it does not fork it.
- **`Med copy/`** — a separate checkout, unrelated to the current build.
- **`dasyante-site/`** — the marketing and investor site for Dasyante (remote:
  `dasyante-site.git`), a static multi-page site with one serverless demo endpoint.

Do not edit files inside these three directories from within `pre/` — commit to them from
their own checkouts.

## Secrets and data

`.env`, `.env.local`, and any file that carries real credentials are gitignored throughout this
repo. `findingframe_deploy_snapshot/` is a deploy snapshot that carries live secrets
(`backend/.env`, `web/.env.local`) — it is gitignored and must never be committed. Before
committing, check staged files for anything that looks like a secret, a credential, or a deploy
snapshot.
