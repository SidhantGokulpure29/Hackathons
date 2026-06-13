# Security Policy

CrisisBrief uses synthetic demo evidence by default. Do not upload production secrets, credentials, private customer data, or regulated personal data into the public demo.

## Reporting Issues

Report security concerns by opening a private advisory or contacting the repository owner directly.

## Data Handling

- Uploaded evidence is stored locally in `data/incidents.json`.
- `.gitignore` excludes local incident data and `.env` secrets.
- The Azure AI Foundry adapter is optional and only sends evidence when credentials are configured.
- Claims without supporting evidence are marked as unknown or missing evidence.
