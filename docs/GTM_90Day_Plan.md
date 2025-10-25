90‑Day GTM Plan (Two Verticals)

Executive Focus
- Verticals: Healthcare (Clinical Ops / SOP Assistant), Financial Services (Policy & Compliance Assistant)
- Outcomes: Reproducible pilots with audit logs, measurable time savings in doc workflows, and path to enterprise add‑ons.

Weeks 1–3: Packaging & Demos
- Deliverables
  - Demo 1 (Healthcare): Ingest SOPs and policy PDFs, /find local mode, summarize with retrieval.
  - Demo 2 (FinServ): Policy/procedure QA over intranet docs, local‑first with audit.
  - “Reproducible Runs” bundle: prebuilt personas, scripts, and validation schemas (docs/schemas).
- Connectors (priority P1)
  - Confluence (export API), SharePoint/OneDrive read‑only, local file trees.
  - Email ingest (IMAP read) for SOP change notices (optional).
- Scripts
  - `scripts/healthcare_demo.sh`: set engine local, ingest folder, run /find + /open flows, show context and logs.
  - `scripts/finserv_demo.sh`: similar structure, tailored prompts and persona.

Weeks 4–6: Pilot Playbooks & Security
- Pilot playbooks per vertical with tasks, metrics, and acceptance criteria.
- Security hardening guides finalized (docs/Security_Hardening_for_Pilots.md).
- Add `qjson-agents validate` to CI demo pipelines; publish GH Action snippet.
- Publish enterprise readiness checklist; add a “pilot Go/No-Go” template.

Weeks 7–9: Connectors & Integrations
- P1 connectors implement read‑only ingestion with clear policy boundaries.
- Export to SIEM (Splunk/ELK) for logs (JSON events and TXT summaries).
- Optional: service catalog entries for on‑prem deployments.

Weeks 10–12: Case Studies & Expansion
- Select 2–3 pilot sites; gather metrics (time saved per task, response latency, % helpful summaries).
- Publish anonymized case studies and demo videos; target procurement.
- Sales enablement: 2‑page collateral per vertical, pricing tiers, and add‑on menu.

Personas & Prompts (starter packs)
- Healthcare:
  - Persona: “Clinical SOP Navigator” (roles: clinician, compliance)
  - Seed Prompts: “Summarize SOP changes for [procedure] and flag training impacts.”
  - Metrics: time to locate SOP clauses, # follow‑ups avoided, accuracy of change notes.
- Financial Services:
  - Persona: “Policy & Compliance Analyst” (roles: risk, audit)
  - Seed Prompts: “What sections mention [control]? Summarize exceptions and timeframes.”
  - Metrics: time‑to‑answer policy questions, coverage breadth, escalation rate.

Connector Roadmap
- P1: Confluence, SharePoint/OneDrive, local FS
- P2: ServiceNow, Jira/GitLab, Slack/Teams read‑only
- P3: GSuite/Drive, Box, Email (advanced threading)

KPIs
- 2 pilot wins per vertical by Day 90
- ≥25% time saved on doc retrieval/summary tasks
- 100% runs validated by schemas in CI
