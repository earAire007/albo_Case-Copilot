import { useEffect, useState } from "react";

import { api, errorText, type Case } from "./api";

const STATUSES = [
  "",
  "queued",
  "proposal_pending",
  "answered",
  "requires_human",
  "approved",
  "rejected",
  "execution_failed",
];

export function Inbox({ onOpen }: { onOpen: (id: string) => void }) {
  const [status, setStatus] = useState("");
  const [cases, setCases] = useState<Case[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load(filter: string) {
    setError(null);
    try {
      setCases(await api.listCases(filter || undefined));
    } catch (e) {
      setError(errorText(e));
    }
  }

  useEffect(() => {
    void load(status);
  }, [status]);

  return (
    <section>
      <h2>Bandeja</h2>
      <label>
        Estado{" "}
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s || "todos"}
            </option>
          ))}
        </select>
      </label>{" "}
      <button onClick={() => void load(status)}>Refrescar</button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <table>
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Cliente</th>
            <th>Estado</th>
            <th>Tipo</th>
            <th>Fecha</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.id} onClick={() => onOpen(c.id)} className="clickable">
              <td>{c.ticket_id}</td>
              <td>{c.customer_id}</td>
              <td>
                <span className="tag">{c.status}</span>
              </td>
              <td>{c.case_type ?? "—"}</td>
              <td>{c.as_of}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {cases.length === 0 && !error && <p className="muted">Sin casos.</p>}
    </section>
  );
}
