import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { Case, TraceRow } from "./api";
import { Detail } from "./Detail";

const CASE: Case = {
  id: "case_1",
  ticket_id: "T-1",
  customer_id: "cus_004",
  status: "proposal_pending",
  as_of: "2026-10-15T12:00:00-06:00",
  message: "Me cobraron dos veces",
  case_type: "card_duplicate_charge",
  reply: "Vamos a abrir una aclaración.",
  final_reply: null,
  edited_by: null,
  edited_at: null,
  reasoning_summary: "Dos cargos idénticos en Liverpool el mismo día.",
  proposal: {
    id: 7,
    action: "open_dispute",
    txn_id: "txn_0166",
    justification: "cargo duplicado",
    decision: null,
    execution: null,
  },
};

const TRACE: TraceRow[] = [
  {
    step: "model_step",
    validator: null,
    created_at: "x",
    payload: {
      input_tokens: 100,
      output_tokens: 50,
      cost_usd: 0.0014,
      latency_ms: 812,
      stop_reason: "tool_use",
      tool_calls: [{ name: "list_transactions", input: '{"type": "card"}' }],
      // Even if a thinking block ever leaked into a payload, the console must not show it.
      thinking: "PENSAMIENTO_SECRETO",
    },
  },
  {
    step: "thinking",
    validator: null,
    created_at: "x",
    payload: { text: "PENSAMIENTO_SECRETO" },
  },
];

function mockFetch() {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const body = url.endsWith("/trace") ? TRACE : url.includes("/approve") ? {} : CASE;
    return new Response(JSON.stringify(body), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

test("shows reasoning and tool calls, never thinking, and approves via the API", async () => {
  const calls = mockFetch();
  render(<Detail caseId="case_1" onBack={() => {}} />);

  expect(await screen.findByTestId("reasoning")).toHaveProperty(
    "textContent",
    CASE.reasoning_summary,
  );
  expect(screen.getByText("list_transactions")).toBeTruthy();
  expect(document.body.textContent).not.toContain("PENSAMIENTO_SECRETO");

  fireEvent.change(screen.getByLabelText(/Operador/), { target: { value: "ana" } });
  fireEvent.click(screen.getByRole("button", { name: "Aprobar" }));

  await waitFor(() => expect(calls.some((c) => c.url === "/api/proposals/7/approve")).toBe(true));
  const approve = calls.find((c) => c.url === "/api/proposals/7/approve")!;
  expect(approve.init?.method).toBe("POST");
  expect(JSON.parse(String(approve.init?.body))).toEqual({ approver: "ana" });
});

test("an approved case whose execution failed offers a retry", async () => {
  const failed: Case = {
    ...CASE,
    status: "execution_failed",
    proposal: {
      ...CASE.proposal!,
      decision: { approver: "ana", decision: "approved", reply_snapshot: null, decided_at: "x" },
    },
  };
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      return new Response(JSON.stringify(url.endsWith("/trace") ? [] : failed), { status: 200 });
    }),
  );
  render(<Detail caseId="case_1" onBack={() => {}} />);
  expect(screen.queryByRole("button", { name: "Aprobar" })).toBeNull();
  fireEvent.click(await screen.findByRole("button", { name: "Reintentar ejecución" }));
  await waitFor(() => expect(calls).toContain("/api/proposals/7/approve"));
});

test("shows the API error message", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return new Response(JSON.stringify({ detail: "la respuesta contiene un tramo de 13 o más dígitos" }), {
          status: 422,
        });
      }
      return new Response(JSON.stringify(url.endsWith("/trace") ? [] : CASE), { status: 200 });
    }),
  );
  render(<Detail caseId="case_1" onBack={() => {}} />);
  fireEvent.click(await screen.findByRole("button", { name: "Guardar" }));
  expect((await screen.findByRole("alert")).textContent).toContain("422");
  expect(screen.getByRole("alert").textContent).toContain("13 o más dígitos");
});
