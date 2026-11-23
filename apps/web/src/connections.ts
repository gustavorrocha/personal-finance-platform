export function visibleConnections<T extends { is_demo: boolean }>(
  connections: T[],
): T[] {
  const imported = connections.filter((connection) => !connection.is_demo);
  return imported.length ? imported : connections;
}
