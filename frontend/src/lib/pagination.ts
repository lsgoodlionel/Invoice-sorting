export const PAGE_SIZE_OPTIONS = [10, 20, 30, 40, 50] as const;

export type PageSize = (typeof PAGE_SIZE_OPTIONS)[number] | 'all';

export const DEFAULT_PAGE_SIZE: PageSize = 10;

export function parsePage(raw: string | null): number {
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : 1;
}

export function parsePageSize(raw: string | null): PageSize {
  if (raw === 'all') return 'all';
  const value = Number(raw);
  return PAGE_SIZE_OPTIONS.includes(value as (typeof PAGE_SIZE_OPTIONS)[number])
    ? value as PageSize
    : DEFAULT_PAGE_SIZE;
}

export function pageCount(total: number, pageSize: PageSize): number {
  return pageSize === 'all' ? 1 : Math.max(1, Math.ceil(total / pageSize));
}

export function pageSlice<T>(items: readonly T[], page: number, pageSize: PageSize): T[] {
  if (pageSize === 'all') return [...items];
  const start = (page - 1) * pageSize;
  return items.slice(start, start + pageSize);
}
