import test from "node:test";
import assert from "node:assert/strict";
import { analyzeIncident } from "../src/analyzer.js";

const incident = {
  id: "test-incident",
  title: "Payment outage",
  documents: [
    {
      id: "notes",
      name: "notes.md",
      content: "09:12 UTC - Support reports failed checkout in East US. 09:29 UTC - Payment adapter 3.18.0 was deployed before errors increased."
    },
    {
      id: "policy",
      name: "policy.md",
      content: "SEV-1 payment incidents require status page updates every 30 minutes until mitigated."
    },
    {
      id: "db",
      name: "db.txt",
      content: "09:41 UTC - Database connection pool saturation appeared on the payment ledger writer."
    }
  ]
};

test("analyzer returns the five required brief sections", () => {
  const brief = analyzeIncident(incident);

  assert.ok(brief.executiveSummary);
  assert.ok(Array.isArray(brief.timeline));
  assert.ok(Array.isArray(brief.rootCauseHypotheses));
  assert.ok(Array.isArray(brief.riskMatrix));
  assert.ok(Array.isArray(brief.actionPlan));
});

test("supported claims include citations", () => {
  const brief = analyzeIncident(incident);
  const claims = [
    brief.executiveSummary,
    ...brief.rootCauseHypotheses,
    ...brief.riskMatrix,
    ...brief.actionPlan
  ];

  for (const claim of claims) {
    if (!claim.uncertain) {
      assert.ok(claim.citations.length > 0, claim.text || claim.finding || claim.action);
    }
  }
});

test("missing evidence is surfaced instead of invented", () => {
  const brief = analyzeIncident({
    id: "thin",
    title: "Thin evidence",
    documents: [
      {
        id: "one",
        name: "one.txt",
        content: "The incident commander opened a review."
      }
    ]
  });

  assert.ok(brief.missingEvidence.length > 0);
  assert.ok(brief.rootCauseHypotheses.some((claim) => claim.uncertain));
});
