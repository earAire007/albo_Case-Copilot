import type { TraceRow } from "./api";

// What the console shows from the trace. Allow-list on purpose: an unknown step is shown
// by name only, never with its payload. Thinking is never persisted (spec 05b); the
// reasoning comes from the structured output (`reasoning_summary`).
type ModelStep = {
  model?: string;
  stop_reason?: string;
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: number;
  latency_ms?: number;
  retries?: number;
  tool_calls?: { name: string; input: string }[];
};

function ModelStepView({ p }: { p: ModelStep }) {
  return (
    <div>
      <strong>Paso del modelo</strong> · {p.input_tokens ?? 0} + {p.output_tokens ?? 0} tokens · $
      {(p.cost_usd ?? 0).toFixed(4)} · {p.latency_ms ?? 0} ms · fin: {p.stop_reason}
      {p.retries ? ` · reintentos: ${p.retries}` : ""}
      {p.tool_calls && p.tool_calls.length > 0 && (
        <ul>
          {p.tool_calls.map((c, i) => (
            <li key={i}>
              <code>{c.name}</code> <code>{c.input}</code>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Row({ row }: { row: TraceRow }) {
  const p = row.payload;
  switch (row.step) {
    case "model_step":
      return <ModelStepView p={p as ModelStep} />;
    case "tool_result":
      return (
        <details>
          <summary>
            Resultado de <code>{String(p.tool)}</code>
          </summary>
          <pre>{JSON.stringify(p.payload, null, 2)}</pre>
        </details>
      );
    case "tool_error":
      return (
        <div className="warn">
          Error en <code>{String(p.tool)}</code> ({String(p.kind)})
        </div>
      );
    case "injection_signal":
      return p.detected ? (
        <div className="warn">
          Señal de injection en {String(p.vector)}: {(p.patterns as string[]).join(", ")}
        </div>
      ) : (
        <div className="muted">Sin señal de injection en {String(p.vector)}</div>
      );
    case "rejection":
      return (
        <div className="warn">
          Rechazo del validador <code>{row.validator}</code>: {String(p.reason ?? "")}
        </div>
      );
    case "stop":
      return <div className="warn">Parada: {String(p.reason)}</div>;
    case "provider_error":
      return (
        <div className="warn">
          Error del proveedor: {String(p.kind)} (intento {String(p.attempt)})
        </div>
      );
    case "validation":
      return <div>Validación: {String(p.status)}</div>;
    case "reasoning_summary":
      return <div>Razonamiento registrado</div>;
    case "answer":
      return <div>Respuesta generada</div>;
    case "proposal":
      return <div>Propuesta creada</div>;
    case "reply_edited":
      return <div>Respuesta editada por {String(p.editor)}</div>;
    case "rejected_by_ops":
      return <div>Rechazada por operaciones: {String(p.reason)}</div>;
    default:
      return <div className="muted">{row.step}</div>;
  }
}

export function Trace({ rows }: { rows: TraceRow[] }) {
  const steps = rows.filter((r) => r.step === "model_step");
  const cost = steps.reduce((sum, r) => sum + Number(r.payload.cost_usd ?? 0), 0);
  const tokens = steps.reduce(
    (sum, r) => sum + Number(r.payload.input_tokens ?? 0) + Number(r.payload.output_tokens ?? 0),
    0,
  );
  return (
    <section>
      <h3>Traza</h3>
      <p className="muted">
        {steps.length} pasos del modelo · {tokens} tokens · ${cost.toFixed(4)}
      </p>
      <ol className="trace">
        {rows.map((row, i) => (
          <li key={i}>
            <Row row={row} />
          </li>
        ))}
      </ol>
    </section>
  );
}
