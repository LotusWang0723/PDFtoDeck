// API client for PDFtoDeck backend

// In dev mode, Next.js rewrites /api/* → localhost:8000/api/*
// In production (Cloudflare), set NEXT_PUBLIC_API_URL to the Workers gateway
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export interface UploadResponse {
  task_id: string;
  pages: number;
  size_mb: number;
}

export interface ConvertResponse {
  status: string;
}

export interface StatusResponse {
  status: "uploaded" | "processing" | "done" | "error";
  progress: number;
  pages: number;
  error?: string;
}

export async function uploadPDF(file: File, email?: string): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const headers: Record<string, string> = {};
  if (email) {
    headers["X-User-Email"] = email;
  }

  const res = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }

  return res.json();
}

export async function startConvert(
  taskId: string,
  iconThreshold: number = 0.05
): Promise<ConvertResponse> {
  const res = await fetch(`${API_BASE}/api/convert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId, icon_threshold: iconThreshold }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Convert failed (${res.status})`);
  }

  return res.json();
}

export async function getStatus(taskId: string): Promise<StatusResponse> {
  const res = await fetch(`${API_BASE}/api/status/${taskId}`);

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Status check failed (${res.status})`);
  }

  return res.json();
}

export function getDownloadUrl(taskId: string): string {
  return `${API_BASE}/api/download/${taskId}`;
}
