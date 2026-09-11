const BASE = "/api";

async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function ingestCsv(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/ingest`, { method: "POST", body: form });
  return handle(res);
}

export async function getStatus(jobId) {
  const res = await fetch(`${BASE}/status?job_id=${encodeURIComponent(jobId)}`);
  return handle(res);
}

export async function getHealth() {
  const res = await fetch(`${BASE}/health`);
  return handle(res);
}

export async function askChat(question, jobId) {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, job_id: jobId || undefined }),
  });
  return handle(res);
}

export async function getInsights(jobId) {
  const res = await fetch(`${BASE}/insights?job_id=${encodeURIComponent(jobId)}`);
  return handle(res);
}

export async function getGraph(jobId, limit = 40) {
  const res = await fetch(`${BASE}/graph?job_id=${encodeURIComponent(jobId)}&limit=${limit}`);
  return handle(res);
}
