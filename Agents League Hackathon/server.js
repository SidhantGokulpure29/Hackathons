import { createServer } from "node:http";
import { readFile, writeFile, mkdir, readdir, stat } from "node:fs/promises";
import { existsSync, createReadStream } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import { analyzeIncident } from "./src/analyzer.js";
import { askFoundryForBrief } from "./src/foundryClient.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(__dirname, "public");
const dataDir = path.join(__dirname, "data");
const incidentsFile = path.join(dataDir, "incidents.json");
const demoEvidenceDir = path.join(__dirname, "demo-evidence");

const contentTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".md": "text/markdown; charset=utf-8"
};

async function ensureStore() {
  await mkdir(dataDir, { recursive: true });
  if (!existsSync(incidentsFile)) {
    await writeFile(incidentsFile, JSON.stringify({ incidents: {} }, null, 2));
  }
}

async function loadStore() {
  await ensureStore();
  return JSON.parse(await readFile(incidentsFile, "utf8"));
}

async function saveStore(store) {
  await ensureStore();
  await writeFile(incidentsFile, JSON.stringify(store, null, 2));
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  if (chunks.length === 0) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function sendJson(response, status, body) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(body));
}

function notFound(response) {
  sendJson(response, 404, { error: "Not found" });
}

function normalizeDocument(input, index) {
  const name = String(input.name || `Evidence ${index + 1}`).trim();
  const content = String(input.content || "").trim();
  const type = String(input.type || "text/plain").trim();
  if (!name || !content) {
    throw new Error("Each document needs a name and content.");
  }
  if (content.length > 80_000) {
    throw new Error(`${name} is too large for the hackathon demo limit.`);
  }
  return {
    id: randomUUID(),
    name,
    type,
    content,
    uploadedAt: new Date().toISOString()
  };
}

async function loadDemoDocuments() {
  const files = await readdir(demoEvidenceDir);
  const documents = [];
  for (const file of files.sort()) {
    const fullPath = path.join(demoEvidenceDir, file);
    const fileStat = await stat(fullPath);
    if (!fileStat.isFile()) continue;
    const content = await readFile(fullPath, "utf8");
    documents.push(normalizeDocument({
      name: file,
      type: path.extname(file) === ".md" ? "text/markdown" : "text/plain",
      content
    }, documents.length));
  }
  return documents;
}

async function handleApi(request, response, url) {
  const store = await loadStore();

  if (request.method === "POST" && url.pathname === "/api/incidents") {
    const body = await readJson(request);
    const id = randomUUID();
    const now = new Date().toISOString();
    store.incidents[id] = {
      id,
      title: body.title || "Payment outage across regions",
      scenario: body.scenario || "Payment outage caused failed checkouts across multiple regions.",
      createdAt: now,
      updatedAt: now,
      documents: body.useDemo ? await loadDemoDocuments() : [],
      brief: null,
      analysisMode: null
    };
    await saveStore(store);
    sendJson(response, 201, store.incidents[id]);
    return;
  }

  const incidentMatch = url.pathname.match(/^\/api\/incidents\/([^/]+)(?:\/([^/]+))?$/);
  if (!incidentMatch) {
    notFound(response);
    return;
  }

  const [, incidentId, action] = incidentMatch;
  const incident = store.incidents[incidentId];
  if (!incident) {
    sendJson(response, 404, { error: "Incident not found" });
    return;
  }

  if (request.method === "GET" && !action) {
    sendJson(response, 200, incident);
    return;
  }

  if (request.method === "POST" && action === "documents") {
    const body = await readJson(request);
    const incoming = Array.isArray(body.documents) ? body.documents : [body];
    const documents = incoming.map(normalizeDocument);
    incident.documents.push(...documents);
    incident.updatedAt = new Date().toISOString();
    await saveStore(store);
    sendJson(response, 201, { documents: incident.documents });
    return;
  }

  if (request.method === "POST" && action === "analyze") {
    const localBrief = analyzeIncident(incident);
    const foundryBrief = await askFoundryForBrief(incident, localBrief);
    incident.brief = foundryBrief.brief;
    incident.analysisMode = foundryBrief.mode;
    incident.updatedAt = new Date().toISOString();
    await saveStore(store);
    sendJson(response, 200, { brief: incident.brief, analysisMode: incident.analysisMode });
    return;
  }

  if (request.method === "GET" && action === "brief") {
    if (!incident.brief) {
      sendJson(response, 404, { error: "Brief has not been generated yet." });
      return;
    }
    sendJson(response, 200, { brief: incident.brief, analysisMode: incident.analysisMode });
    return;
  }

  notFound(response);
}

async function serveStatic(response, url) {
  const requested = url.pathname === "/" ? "/index.html" : url.pathname;
  const safePath = path.normalize(requested).replace(/^(\.\.[/\\])+/, "");
  const filePath = path.join(publicDir, safePath);
  if (!filePath.startsWith(publicDir) || !existsSync(filePath)) {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found");
    return;
  }
  response.writeHead(200, { "content-type": contentTypes[path.extname(filePath)] || "application/octet-stream" });
  createReadStream(filePath).pipe(response);
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, `http://${request.headers.host}`);
    if (url.pathname.startsWith("/api/")) {
      await handleApi(request, response, url);
      return;
    }
    await serveStatic(response, url);
  } catch (error) {
    sendJson(response, 500, { error: error.message || "Unexpected error" });
  }
});

const port = Number(process.env.PORT || 3000);
server.listen(port, () => {
  console.log(`CrisisBrief running at http://localhost:${port}`);
});
