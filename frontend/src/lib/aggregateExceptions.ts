// Fetches every exception for a run (paginated, bounded) purely to compute a
// client-side COUNT per category for the Exception Health chart (Phase 6).
// This is aggregation of already-real per-item data, never a fabricated or
// hardcoded distribution, and never a financial sum -- just counting.
import { api } from "../api/client";
import type { ExceptionListItem } from "../api/types";

const PAGE_SIZE = 100;
const MAX_PAGES = 10; // hard ceiling (1,000 records) so a misbehaving API can never cause unbounded fetching

export async function fetchAllExceptionsForRun(runId: string): Promise<ExceptionListItem[]> {
  const items: ExceptionListItem[] = [];
  let page = 1;
  while (page <= MAX_PAGES) {
    const response = await api.listExceptions({ run_id: runId, page, page_size: PAGE_SIZE });
    items.push(...response.items);
    if (items.length >= response.total || response.items.length === 0) break;
    page += 1;
  }
  return items;
}

export interface CategoryCount {
  category: string;
  count: number;
}

export function countByCategory(items: ExceptionListItem[]): CategoryCount[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const key = item.category ?? "clean / exact match";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count);
}
