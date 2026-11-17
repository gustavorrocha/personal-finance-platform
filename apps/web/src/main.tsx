import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { checkHealth } from "./health";
import "./style.css";

function App() {
  const [status, setStatus] = useState("Verificando ambiente…");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    setStatus(await checkHealth());
    setBusy(false);
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <main>
      <p className="eyebrow">FINANÇAS PESSOAIS · LOCAL</p>
      <h1>Seu ambiente privado</h1>
      <p>
        A estrutura está pronta para avaliação. Nenhuma conta bancária está
        conectada.
      </p>
      <section aria-labelledby="status-title">
        <h2 id="status-title">Estado do ambiente</h2>
        <p role="status" aria-live="polite" aria-busy={busy}>
          {status}
        </p>
        <button onClick={() => void refresh()} disabled={busy}>
          {busy ? "Verificando…" : "Verificar novamente"}
        </button>
      </section>
      <footer>Fase 0 · Somente dados sintéticos</footer>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
