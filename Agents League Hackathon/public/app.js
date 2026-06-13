let currentIncident = null;
let currentBrief = null;
let popover = null;

const elements = {
  modePill: document.querySelector("#modePill"),
  demoButton: document.querySelector("#demoButton"),
  createButton: document.querySelector("#createButton"),
  addDocButton: document.querySelector("#addDocButton"),
  analyzeButton: document.querySelector("#analyzeButton"),
  exportButton: document.querySelector("#exportButton"),
  incidentTitle: document.querySelector("#incidentTitle"),
  incidentScenario: document.querySelector("#incidentScenario"),
  docName: document.querySelector("#docName"),
  docContent: document.querySelector("#docContent"),
  documentList: document.querySelector("#documentList"),
  briefTitle: document.querySelector("#briefTitle"),
  emptyState: document.querySelector("#emptyState"),
  briefOutput: document.querySelector("#briefOutput")
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "content-type": "application/json",
      ...(options.headers || {})
    }
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Request failed");
  return payload;
}

function setMode(text) {
  elements.modePill.textContent = text;
}

function citationButtons(citations = []) {
  if (!citations.length) return `<span class="pill">Unverified</span>`;
  return citations.map((citation) => {
    const encoded = encodeURIComponent(JSON.stringify(citation));
    return `<button class="citation" type="button" data-citation="${encoded}">${citation.source}</button>`;
  }).join("");
}

function claimHtml(claim) {
  return `
    <div class="claim ${claim.uncertain ? "uncertain" : ""}">
      <div>${claim.text || claim.finding || claim.action || ""}</div>
      <div class="citation-row">${citationButtons(claim.citations)}</div>
    </div>
  `;
}

function renderDocuments() {
  elements.documentList.innerHTML = "";
  const documents = currentIncident?.documents || [];
  if (!documents.length) {
    elements.documentList.innerHTML = "<li>No evidence uploaded yet.</li>";
    return;
  }
  for (const documentItem of documents) {
    const item = document.createElement("li");
    item.innerHTML = `${documentItem.name}<span>${documentItem.content.length.toLocaleString()} characters</span>`;
    elements.documentList.append(item);
  }
}

function renderIncident() {
  elements.addDocButton.disabled = !currentIncident;
  elements.analyzeButton.disabled = !currentIncident || currentIncident.documents.length === 0;
  elements.briefTitle.textContent = currentIncident ? currentIncident.title : "No workspace yet";
  renderDocuments();
}

function renderBrief(payload) {
  currentBrief = payload.brief;
  elements.exportButton.disabled = false;
  elements.emptyState.classList.add("hidden");
  elements.briefOutput.classList.remove("hidden");
  const brief = payload.brief;

  elements.briefOutput.innerHTML = `
    <section class="brief-card">
      <h3>Executive Summary</h3>
      ${claimHtml(brief.executiveSummary)}
      <p class="pill">${brief.iqLayer || payload.analysisMode}</p>
    </section>

    <section class="brief-card">
      <h3>Timeline</h3>
      <div class="table">
        ${(brief.timeline || []).map((event) => `
          <div class="table-row ${event.uncertain ? "uncertain" : ""}">
            <div class="time">${event.time}</div>
            <div>
              <div>${event.event}</div>
              <div class="citation-row">${citationButtons(event.citations)}</div>
            </div>
          </div>
        `).join("")}
      </div>
    </section>

    <section class="grid-two">
      <div class="brief-card">
        <h3>Root-Cause Hypotheses</h3>
        ${(brief.rootCauseHypotheses || []).map(claimHtml).join("")}
      </div>
      <div class="brief-card">
        <h3>Risk Matrix</h3>
        ${(brief.riskMatrix || []).map((risk) => `
          <div class="claim ${risk.uncertain ? "uncertain" : ""}">
            <div><strong>${risk.area}</strong> <span class="severity">${risk.severity}</span></div>
            <div>${risk.finding}</div>
            <div class="citation-row">${citationButtons(risk.citations)}</div>
          </div>
        `).join("")}
      </div>
    </section>

    <section class="brief-card">
      <h3>Action Plan</h3>
      ${(brief.actionPlan || []).map((action) => `
        <div class="claim ${action.uncertain ? "uncertain" : ""}">
          <div><strong>${action.priority}</strong> ${action.owner}: ${action.action}</div>
          <div class="citation-row">${citationButtons(action.citations)}</div>
        </div>
      `).join("")}
    </section>

    <section class="grid-two">
      <div class="brief-card">
        <h3>Missing Evidence</h3>
        ${(brief.missingEvidence || []).map((question) => `<div class="claim uncertain">${question}</div>`).join("") || "<p>No major gaps detected.</p>"}
      </div>
      <div class="brief-card">
        <h3>Reliability Notes</h3>
        ${(brief.reliabilityNotes || []).map((note) => `<div class="claim">${note}</div>`).join("")}
      </div>
    </section>
  `;
}

async function createIncident(useDemo = false) {
  setMode("Creating");
  currentIncident = await api("/api/incidents", {
    method: "POST",
    body: JSON.stringify({
      title: elements.incidentTitle.value,
      scenario: elements.incidentScenario.value,
      useDemo
    })
  });
  currentBrief = null;
  elements.exportButton.disabled = true;
  elements.emptyState.classList.remove("hidden");
  elements.briefOutput.classList.add("hidden");
  renderIncident();
  setMode(useDemo ? "Demo loaded" : "Workspace ready");
}

async function addDocument() {
  if (!currentIncident) return;
  setMode("Uploading");
  const payload = await api(`/api/incidents/${currentIncident.id}/documents`, {
    method: "POST",
    body: JSON.stringify({
      name: elements.docName.value,
      content: elements.docContent.value
    })
  });
  currentIncident.documents = payload.documents;
  elements.docName.value = "";
  elements.docContent.value = "";
  renderIncident();
  setMode("Evidence added");
}

async function analyze() {
  if (!currentIncident) return;
  setMode("Analyzing");
  elements.analyzeButton.disabled = true;
  const payload = await api(`/api/incidents/${currentIncident.id}/analyze`, { method: "POST", body: "{}" });
  renderBrief(payload);
  elements.analyzeButton.disabled = false;
  setMode(payload.analysisMode);
}

function exportBrief() {
  if (!currentBrief) return;
  const blob = new Blob([JSON.stringify(currentBrief, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "crisisbrief-report.json";
  link.click();
  URL.revokeObjectURL(url);
}

function showCitation(event) {
  const button = event.target.closest("[data-citation]");
  if (!button) return;
  const citation = JSON.parse(decodeURIComponent(button.dataset.citation));
  popover?.remove();
  popover = document.createElement("div");
  popover.className = "quote-popover";
  popover.innerHTML = `<strong>${citation.source}</strong>${citation.quote}`;
  document.body.append(popover);
  const rect = button.getBoundingClientRect();
  popover.style.left = `${Math.min(rect.left, window.innerWidth - popover.offsetWidth - 14)}px`;
  popover.style.top = `${rect.bottom + 8}px`;
}

document.addEventListener("click", (event) => {
  if (!event.target.closest("[data-citation]")) popover?.remove();
});
elements.briefOutput.addEventListener("click", showCitation);
elements.createButton.addEventListener("click", () => createIncident(false).catch((error) => setMode(error.message)));
elements.demoButton.addEventListener("click", () => createIncident(true).then(analyze).catch((error) => setMode(error.message)));
elements.addDocButton.addEventListener("click", () => addDocument().catch((error) => setMode(error.message)));
elements.analyzeButton.addEventListener("click", () => analyze().catch((error) => setMode(error.message)));
elements.exportButton.addEventListener("click", exportBrief);

renderIncident();
