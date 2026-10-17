// HTTP client for the copilot API (spec 06/07). The console never imports backend code.

export type Decision = {
  approver: string;
  decision: "approved" | "rejected";
  reply_snapshot: string | null;
  decided_at: string;
};

export type Execution = { result: Record<string, unknown>; executed_at: string };

export type Proposal = {
  id: number;
  action: string;
  txn_id: string;
  justification: string;
  decision: Decision | null;
  execution: Execution | null;
};

export type Case = {
  id: string;
  ticket_id: string;
  customer_id: string;
  status: string;
  // Only for requires_human / execution_failed: fixed ops catalog, never raw errors.
  status_reason: string | null;
  as_of: string;
  message: string;
  case_type: string | null;
  reply: string | null;
  final_reply: string | null;
  edited_by: string | null;
  edited_at: string | null;
  reasoning_summary: string | null;
  proposal: Proposal | null;
};

export type TraceRow = {
  step: string;
  validator: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, detailOf(body) ?? `error ${response.status}`);
  }
  return body as T;
}

function detailOf(body: unknown): string | null {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    // FastAPI validation errors: a list of {msg, loc}.
    if (Array.isArray(detail)) {
      return detail.map((d) => (d as { msg?: string }).msg ?? "dato inválido").join("; ");
    }
  }
  return null;
}

export const api = {
  listCases: (status?: string) =>
    request<Case[]>(`/cases${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  getCase: (id: string) => request<Case>(`/cases/${encodeURIComponent(id)}`),
  getTrace: (id: string) => request<TraceRow[]>(`/cases/${encodeURIComponent(id)}/trace`),
  editReply: (id: string, editor: string, finalReply: string) =>
    request<Case>(`/cases/${encodeURIComponent(id)}/reply`, {
      method: "PUT",
      body: JSON.stringify({ editor, final_reply: finalReply }),
    }),
  approve: (proposalId: number, approver: string) =>
    request<unknown>(`/proposals/${proposalId}/approve`, {
      method: "POST",
      body: JSON.stringify({ approver }),
    }),
  reject: (proposalId: number, approver: string, reason: string) =>
    request<unknown>(`/proposals/${proposalId}/reject`, {
      method: "POST",
      body: JSON.stringify({ approver, reason }),
    }),
};

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return `${error.status}: ${error.message}`;
  return error instanceof Error ? error.message : String(error);
}
