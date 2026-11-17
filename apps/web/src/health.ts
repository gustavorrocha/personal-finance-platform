export async function checkHealth(): Promise<string> {
  try {
    const response = await fetch("/health", {
      signal: AbortSignal.timeout(5000),
    });
    const health: unknown = await response.json();
    if (
      response.ok &&
      typeof health === "object" &&
      health !== null &&
      "status" in health &&
      health.status === "ok" &&
      "phase" in health &&
      health.phase === 0
    )
      return "Ambiente disponível";
  } catch {
    // Do not show internal errors or request values in the browser.
  }
  return "Ambiente indisponível. Verifique os serviços locais.";
}
