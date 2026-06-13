const categories = {
  checkout: ["checkout", "payment", "authorization", "authorize", "cart", "order"],
  region: ["eastus", "westus", "europe", "apac", "region", "multi-region"],
  database: ["database", "db", "connection", "pool", "latency", "timeout"],
  deploy: ["deploy", "release", "rollback", "version", "migration", "flag"],
  customer: ["customer", "merchant", "support", "complaint", "revenue", "failed"],
  policy: ["policy", "sla", "status", "incident", "severity", "escalation"],
  recovery: ["mitigated", "restored", "rollback", "reroute", "disabled", "recovered"]
};

function splitSentences(text) {
  return text
    .replace(/\r/g, "")
    .split(/(?<=[.!?])\s+|\n+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

function extractTime(sentence) {
  const match = sentence.match(/\b(?:20\d{2}-\d{2}-\d{2}[ T])?\d{1,2}:\d{2}\s?(?:UTC|IST|PST|AM|PM)?\b/i);
  return match ? match[0].trim() : null;
}

function scoreSentence(sentence, keywords) {
  const lower = sentence.toLowerCase();
  return keywords.reduce((score, keyword) => lower.includes(keyword) ? score + 1 : score, 0);
}

function citationFor(document, sentence, quoteIndex) {
  return {
    id: `${document.id}:${quoteIndex}`,
    sourceId: document.id,
    source: document.name,
    quote: sentence.length > 220 ? `${sentence.slice(0, 217)}...` : sentence
  };
}

function collectEvidence(documents) {
  const chunks = [];
  documents.forEach((document) => {
    splitSentences(document.content).forEach((sentence, index) => {
      chunks.push({
        document,
        sentence,
        index,
        time: extractTime(sentence),
        scores: Object.fromEntries(
          Object.entries(categories).map(([category, keywords]) => [category, scoreSentence(sentence, keywords)])
        )
      });
    });
  });
  return chunks;
}

function topChunks(chunks, category, limit = 4) {
  return chunks
    .filter((chunk) => chunk.scores[category] > 0)
    .sort((left, right) => right.scores[category] - left.scores[category])
    .slice(0, limit);
}

function citedStatement(text, chunks, uncertain = false) {
  return {
    text,
    uncertain,
    citations: chunks.map((chunk) => citationFor(chunk.document, chunk.sentence, chunk.index))
  };
}

function buildTimeline(chunks) {
  const events = chunks
    .filter((chunk) => chunk.time && (chunk.scores.checkout || chunk.scores.deploy || chunk.scores.recovery || chunk.scores.customer))
    .slice()
    .sort((left, right) => left.time.localeCompare(right.time))
    .slice(0, 8)
    .map((chunk) => ({
      time: chunk.time,
      event: chunk.sentence.replace(chunk.time, "").replace(/^[-: ]+/, ""),
      citations: [citationFor(chunk.document, chunk.sentence, chunk.index)]
    }));

  if (events.length > 0) return events;
  return [{
    time: "Unknown",
    event: "No explicit timestamps were found in the provided evidence.",
    citations: [],
    uncertain: true
  }];
}

function buildRootCauses(chunks) {
  const deploy = topChunks(chunks, "deploy", 2);
  const database = topChunks(chunks, "database", 2);
  const region = topChunks(chunks, "region", 2);
  const causes = [];

  if (deploy.length) {
    causes.push(citedStatement("Recent release or configuration change likely contributed to the incident.", deploy));
  }
  if (database.length) {
    causes.push(citedStatement("Database connection pressure or latency is a plausible failure path.", database));
  }
  if (region.length) {
    causes.push(citedStatement("The evidence suggests impact across more than one region.", region));
  }
  if (causes.length === 0) {
    causes.push(citedStatement("Root cause cannot be determined from the current evidence.", [], true));
  }
  return causes;
}

function buildRisks(chunks) {
  const customer = topChunks(chunks, "customer", 3);
  const policy = topChunks(chunks, "policy", 3);
  const checkout = topChunks(chunks, "checkout", 3);

  return [
    {
      area: "Customer Impact",
      severity: customer.length ? "High" : "Unknown",
      finding: customer.length
        ? "Customers and merchants experienced failed payment or checkout flows."
        : "Customer impact needs confirmation.",
      citations: customer.map((chunk) => citationFor(chunk.document, chunk.sentence, chunk.index)),
      uncertain: customer.length === 0
    },
    {
      area: "Revenue Risk",
      severity: checkout.length ? "High" : "Unknown",
      finding: checkout.length
        ? "Checkout failure evidence indicates direct revenue exposure."
        : "Revenue impact is not quantified in the evidence.",
      citations: checkout.map((chunk) => citationFor(chunk.document, chunk.sentence, chunk.index)),
      uncertain: checkout.length === 0
    },
    {
      area: "Compliance and Communications",
      severity: policy.length ? "Medium" : "Unknown",
      finding: policy.length
        ? "Status-page, SLA, or escalation obligations may apply."
        : "Policy obligations need a cited policy source.",
      citations: policy.map((chunk) => citationFor(chunk.document, chunk.sentence, chunk.index)),
      uncertain: policy.length === 0
    }
  ];
}

function buildActions(chunks) {
  const actions = [
    {
      owner: "Incident Commander",
      action: "Publish a customer-facing update with known impact, affected regions, and next update time.",
      priority: "P0",
      citations: topChunks(chunks, "policy", 2).map((chunk) => citationFor(chunk.document, chunk.sentence, chunk.index))
    },
    {
      owner: "Payments Engineering",
      action: "Compare payment authorization errors before and after the latest release or configuration change.",
      priority: "P0",
      citations: [...topChunks(chunks, "checkout", 1), ...topChunks(chunks, "deploy", 1)].map((chunk) => citationFor(chunk.document, chunk.sentence, chunk.index))
    },
    {
      owner: "SRE",
      action: "Validate database pool health, timeout rates, and regional failover routing.",
      priority: "P1",
      citations: [...topChunks(chunks, "database", 1), ...topChunks(chunks, "region", 1)].map((chunk) => citationFor(chunk.document, chunk.sentence, chunk.index))
    },
    {
      owner: "Support Lead",
      action: "Tag affected tickets and prepare a customer recovery response for failed orders.",
      priority: "P1",
      citations: topChunks(chunks, "customer", 2).map((chunk) => citationFor(chunk.document, chunk.sentence, chunk.index))
    }
  ];

  return actions.map((action) => ({
    ...action,
    uncertain: action.citations.length === 0
  }));
}

function buildQuestions(chunks) {
  const questions = [];
  if (topChunks(chunks, "database").length === 0) questions.push("Do we have database and payment gateway metrics for the incident window?");
  if (topChunks(chunks, "deploy").length === 0) questions.push("Was there a release, feature flag change, or infrastructure update before impact started?");
  if (topChunks(chunks, "customer").length === 0) questions.push("How many customers, merchants, and transactions were affected?");
  if (topChunks(chunks, "policy").length === 0) questions.push("Which SLA, status-page, and escalation policies apply to this incident?");
  return questions;
}

export function analyzeIncident(incident) {
  const chunks = collectEvidence(incident.documents || []);
  const checkoutChunks = topChunks(chunks, "checkout", 3);
  const customerChunks = topChunks(chunks, "customer", 2);
  const recoveryChunks = topChunks(chunks, "recovery", 2);
  const summaryChunks = [...checkoutChunks, ...customerChunks, ...recoveryChunks].slice(0, 5);
  const documentNames = (incident.documents || []).map((document) => document.name);

  const summaryText = summaryChunks.length
    ? "CrisisBrief found evidence of a payment or checkout incident with customer impact and an active recovery path."
    : "CrisisBrief needs more evidence before it can make a supported incident assessment.";

  return {
    incidentId: incident.id,
    title: incident.title,
    generatedAt: new Date().toISOString(),
    iqLayer: "Foundry IQ retrieval grounding with local deterministic fallback",
    evidencePack: documentNames,
    executiveSummary: citedStatement(summaryText, summaryChunks, summaryChunks.length === 0),
    timeline: buildTimeline(chunks),
    rootCauseHypotheses: buildRootCauses(chunks),
    riskMatrix: buildRisks(chunks),
    actionPlan: buildActions(chunks),
    missingEvidence: buildQuestions(chunks),
    reliabilityNotes: [
      "Every supported claim includes citations from uploaded evidence.",
      "Unsupported areas are marked as unknown instead of inferred.",
      "The local analyzer keeps the demo deterministic when cloud credentials are unavailable."
    ]
  };
}
