export class LabError extends Error {
  constructor(code, requestId = null) {
    super(code);
    this.code = code;
    this.requestId = requestId;
  }
}

async function checkedResponse(response) {
  if (response.ok) return response;
  const payload = await response.json().catch(() => ({}));
  throw new LabError(payload.error?.code || "http_error", payload.error?.request_id);
}

export async function getJSON(path, options = {}) {
  const response = await checkedResponse(await fetch(path, {cache: "no-store", ...options}));
  return response.json();
}

export async function readRun(runId, waitForClose = false) {
  const path = `/api/lab/runs/${encodeURIComponent(runId)}`;
  let run = await getJSON(path);
  for (let attempt = 0; waitForClose && run.status === "running" && attempt < 8; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 150));
    run = await getJSON(path);
  }
  return run;
}

export async function streamJSON(path, payload, signal, onRecord) {
  const response = await checkedResponse(await fetch(path, {method: "POST", signal,
    headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)}));
  if (!response.body) throw new LabError("stream_unavailable");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let terminal = false;
  try {
    while (true) {
      const {value, done} = await reader.read();
      buffer += decoder.decode(value, {stream: !done});
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const record = JSON.parse(line);
        if (terminal) throw new LabError("invalid_stream");
        terminal = record.type === "result" || record.type === "error";
        await onRecord(record);
      }
      if (done) break;
    }
    if (buffer.trim() || !terminal) throw new LabError("stream_interrupted");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
