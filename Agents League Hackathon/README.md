# CrisisBrief

CrisisBrief is a Reasoning Agent for the Agents League Hackathon. It turns messy incident evidence into a cited executive crisis brief with timeline, root-cause hypotheses, risk matrix, missing evidence, and action plan.

Track: Reasoning Agents  
IQ integration: Azure AI Foundry / Foundry IQ retrieval-grounded reasoning, with a deterministic local cited fallback for demos.

## Features

- Incident workspace with seeded payment-outage demo evidence.
- Evidence upload for notes, logs, policy snippets, support digests, and postmortem fragments.
- Five-part crisis brief: executive summary, timeline, root causes, risk matrix, and action plan.
- Citation chips beside major claims, with source quotes visible in the UI.
- Safety behavior that marks unknowns and missing evidence instead of inventing unsupported facts.
- Optional Azure AI Foundry adapter via environment variables.

## Architecture

- Browser UI in `public/` renders the incident workspace and cited brief.
- Node API in `server.js` exposes the required incident routes.
- Local analyzer in `src/analyzer.js` chunks evidence, extracts incident signals, and attaches citations.
- Foundry adapter in `src/foundryClient.js` calls an Azure-hosted model when credentials are configured.
- Demo evidence in `demo-evidence/` provides a realistic payment outage packet.

```text
Evidence Upload -> Incident API -> Analyzer / Foundry Adapter -> Structured Brief -> Cited UI
```

## Setup

Requires Node.js 20 or newer.

```bash
npm install
npm start
```

Open `http://localhost:3000`.

No external dependencies are required for the local demo path.

## Azure AI Foundry Configuration

The app runs without cloud credentials. To route analysis through an Azure AI Foundry-compatible deployment, set:

```bash
AZURE_AI_FOUNDRY_ENDPOINT=https://<resource>.openai.azure.com
AZURE_AI_FOUNDRY_DEPLOYMENT=<deployment-name>
AZURE_AI_FOUNDRY_API_KEY=<key>
AZURE_AI_FOUNDRY_API_VERSION=2024-10-21
```

Then restart the server and run analysis again. The UI status pill reports `azure-ai-foundry` when the cloud path succeeds.

## Usage

1. Click `Load Demo Incident`.
2. Review the uploaded outage packet in the document list.
3. Inspect the generated crisis brief.
4. Click citation chips to view the exact evidence quotes.
5. Export the report JSON for submission artifacts or screenshots.

## API

- `POST /api/incidents` creates an incident workspace.
- `POST /api/incidents/:id/documents` uploads evidence documents.
- `POST /api/incidents/:id/analyze` generates the cited crisis brief.
- `GET /api/incidents/:id/brief` returns the latest structured brief.

## Judging Criteria Alignment

- Accuracy and relevance: claims are grounded in uploaded evidence.
- Reasoning and multi-step thinking: the brief connects timeline, symptoms, root-cause hypotheses, risks, and next actions.
- Creativity and originality: the app turns incident chaos into an executive-ready crisis room.
- User experience and presentation: a polished workspace makes citations and uncertainty visible.
- Reliability and safety: unsupported claims are marked unknown and missing evidence is surfaced explicitly.
- Community vote: the demo scenario is understandable in under two minutes.

## Submitted Demo Evidence

The hackathon submission used screenshots/images from the running local app at `http://localhost:3000` rather than a recorded demo video.

The submitted images show:

1. The CrisisBrief workspace after loading the seeded payment outage incident.
2. The generated executive summary, timeline, root-cause hypotheses, risk matrix, and action plan.
3. Citation chips that connect major claims back to uploaded evidence.
4. Missing evidence and safety notes that show the app avoids unsupported claims.

To reproduce the submitted screenshots:

1. Run `npm start`.
2. Open `http://localhost:3000`.
3. Click `Load Demo Incident`.
4. Capture the generated crisis brief and citation views.

## Policies

This repository is prepared for a public hackathon submission. The demo data is synthetic and contains no real customer or production information.

License: MIT
