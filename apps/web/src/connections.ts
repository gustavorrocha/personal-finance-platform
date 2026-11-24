export function visibleConnections<T extends { is_demo: boolean }>(
  connections: T[],
): T[] {
  const imported = connections.filter((connection) => !connection.is_demo);
  return imported.length ? imported : connections;
}

type Named = { id: string; is_demo: boolean; institution?: string | null };

/** The institution's name, numbered when two connections share it. */
export function connectionLabel(
  connections: Named[],
  connection: Named,
  fallback: string,
  demo: string,
): string {
  if (connection.is_demo) return demo;
  const name = connection.institution || fallback;
  const same = connections.filter(
    (other) => !other.is_demo && (other.institution || fallback) === name,
  );
  return same.length > 1 ? `${name} ${same.indexOf(connection) + 1}` : name;
}
