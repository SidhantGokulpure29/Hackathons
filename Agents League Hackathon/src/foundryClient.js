function hasFoundryConfig() {
  return Boolean(
    process.env.AZURE_AI_FOUNDRY_ENDPOINT &&
    process.env.AZURE_AI_FOUNDRY_DEPLOYMENT &&
    (process.env.AZURE_AI_FOUNDRY_API_KEY || process.env.AZURE_OPENAI_API_KEY)
  );
}

function buildPrompt(incident, localBrief) {
  const evidence = (incident.documents || [])
    .map((document) => `SOURCE: ${document.name}\n${document.content.slice(0, 6000)}`)
    .join("\n\n---\n\n");
  return [
    "You are CrisisBrief, a reliability-focused incident reasoning agent.",
    "Return only JSON with the same shape as the draft brief.",
    "Keep citations tied to source names and do not add claims without evidence.",
    "Mark uncertain fields when evidence is missing.",
    `Draft brief:\n${JSON.stringify(localBrief, null, 2)}`,
    `Evidence:\n${evidence}`
  ].join("\n\n");
}

export async function askFoundryForBrief(incident, localBrief) {
  if (!hasFoundryConfig()) {
    return { mode: "local-cited-fallback", brief: localBrief };
  }

  const endpoint = process.env.AZURE_AI_FOUNDRY_ENDPOINT.replace(/\/$/, "");
  const deployment = encodeURIComponent(process.env.AZURE_AI_FOUNDRY_DEPLOYMENT);
  const apiVersion = process.env.AZURE_AI_FOUNDRY_API_VERSION || "2024-10-21";
  const apiKey = process.env.AZURE_AI_FOUNDRY_API_KEY || process.env.AZURE_OPENAI_API_KEY;
  const url = `${endpoint}/openai/deployments/${deployment}/chat/completions?api-version=${apiVersion}`;

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "api-key": apiKey
      },
      body: JSON.stringify({
        messages: [
          {
            role: "system",
            content: "You produce cited, cautious incident briefs for executives and responders."
          },
          {
            role: "user",
            content: buildPrompt(incident, localBrief)
          }
        ],
        temperature: 0.2,
        response_format: { type: "json_object" }
      })
    });

    if (!response.ok) {
      return {
        mode: `local-fallback-foundry-error-${response.status}`,
        brief: {
          ...localBrief,
          foundryWarning: `Foundry request failed with HTTP ${response.status}; using local cited fallback.`
        }
      };
    }

    const payload = await response.json();
    const content = payload.choices?.[0]?.message?.content;
    if (!content) return { mode: "local-fallback-empty-foundry-response", brief: localBrief };
    return { mode: "azure-ai-foundry", brief: JSON.parse(content) };
  } catch (error) {
    return {
      mode: "local-fallback-foundry-exception",
      brief: {
        ...localBrief,
        foundryWarning: `Foundry request failed: ${error.message}`
      }
    };
  }
}
