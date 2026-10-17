import { useEffect, useState } from "react";

import { Detail } from "./Detail";
import { Inbox } from "./Inbox";

// Hash routing (#/cases/<id>): no router dependency for two views.
function caseFromHash(): string | null {
  const match = window.location.hash.match(/^#\/cases\/(.+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

export function App() {
  const [caseId, setCaseId] = useState(caseFromHash);

  useEffect(() => {
    const onHash = () => setCaseId(caseFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  return (
    <main>
      <h1>Copiloto de casos</h1>
      {caseId ? (
        <Detail caseId={caseId} onBack={() => (window.location.hash = "")} />
      ) : (
        <Inbox onOpen={(id) => (window.location.hash = `/cases/${encodeURIComponent(id)}`)} />
      )}
    </main>
  );
}
