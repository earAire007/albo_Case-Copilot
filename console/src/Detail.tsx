import { useCallback, useEffect, useState } from "react";

import { api, errorText, type Case, type TraceRow } from "./api";
import { Trace } from "./Trace";

export function Detail({ caseId, onBack }: { caseId: string; onBack: () => void }) {
  const [data, setData] = useState<Case | null>(null);
  const [trace, setTrace] = useState<TraceRow[]>([]);
  const [draft, setDraft] = useState("");
  const [operator, setOperator] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [c, t] = await Promise.all([api.getCase(caseId), api.getTrace(caseId)]);
      setData(c);
      setTrace(t);
      setDraft(c.final_reply ?? c.reply ?? "");
    } catch (e) {
      setError(errorText(e));
    }
  }, [caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(action: () => Promise<unknown>, done: string) {
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(done);
      await load();
    } catch (e) {
      setError(errorText(e));
    }
  }

  if (!data) {
    return <p>{error ? <span role="alert">{error}</span> : "Cargando…"}</p>;
  }
  const proposal = data.proposal;
  const decided = proposal?.decision != null;

  return (
    <article>
      <button onClick={onBack}>← Bandeja</button>
      <h2>
        Ticket {data.ticket_id} · {data.customer_id} · <span className="tag">{data.status}</span>
      </h2>
      {data.status_reason && (
        <p className="warn" data-testid="status-reason">
          Motivo: {data.status_reason}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && <p className="ok">{notice}</p>}

      <label>
        Operador{" "}
        <input value={operator} onChange={(e) => setOperator(e.target.value)} />
      </label>

      <section>
        <h3>Mensaje del cliente</h3>
        <blockquote>{data.message}</blockquote>
        <p>
          Tipo de caso: <strong>{data.case_type ?? "—"}</strong>
        </p>
        <h3>Razonamiento del agente</h3>
        <p data-testid="reasoning">{data.reasoning_summary ?? "—"}</p>
      </section>

      <section>
        <h3>Respuesta</h3>
        <p className="muted">Propuesta por el modelo:</p>
        <blockquote>{data.reply ?? "—"}</blockquote>
        <label htmlFor="final-reply">Respuesta final</label>
        <textarea
          id="final-reply"
          rows={5}
          value={draft}
          disabled={decided}
          onChange={(e) => setDraft(e.target.value)}
        />
        {data.edited_by && (
          <p className="muted">
            Editada por {data.edited_by} · {data.edited_at}
          </p>
        )}
        <button
          disabled={decided}
          onClick={() => run(() => api.editReply(data.id, operator, draft), "Respuesta guardada")}
        >
          Guardar
        </button>
      </section>

      {proposal && (
        <section>
          <h3>Acción propuesta</h3>
          <p>
            <code>{proposal.action}</code> sobre <code>{proposal.txn_id}</code>
          </p>
          <p>{proposal.justification}</p>
          {proposal.decision ? (
            <div>
              <p>
                Decisión: <strong>{proposal.decision.decision}</strong> por{" "}
                {proposal.decision.approver} · {proposal.decision.decided_at}
              </p>
              {proposal.execution && (
                <pre>{JSON.stringify(proposal.execution.result, null, 2)}</pre>
              )}
              {data.status === "execution_failed" && (
                <div className="actions">
                  <button
                    onClick={() =>
                      run(() => api.approve(proposal.id, operator), "Ejecución registrada")
                    }
                  >
                    Reintentar ejecución
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="actions">
              <button
                onClick={() =>
                  run(() => api.approve(proposal.id, operator), "Propuesta aprobada")
                }
              >
                Aprobar
              </button>
              <input
                placeholder="Motivo del rechazo"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <button
                onClick={() =>
                  run(() => api.reject(proposal.id, operator, reason), "Propuesta rechazada")
                }
              >
                Rechazar
              </button>
            </div>
          )}
        </section>
      )}

      <Trace rows={trace} />
    </article>
  );
}
