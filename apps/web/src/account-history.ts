export type AccountHistory = {
  observations: {
    observed_at: string;
    balance: string | null;
    currency: string | null;
  }[];
  truncated: boolean;
};

export async function fetchAccountHistory(
  item: string,
  account: string,
  signal: AbortSignal,
  limit?: 200,
): Promise<AccountHistory | null> {
  const query = new URLSearchParams({ item, account });
  if (limit !== undefined) query.set("limit", String(limit));
  const response = await fetch(`/api/accounts/history?${query}`, { signal });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("Account history request failed");
  return (await response.json()) as AccountHistory;
}
