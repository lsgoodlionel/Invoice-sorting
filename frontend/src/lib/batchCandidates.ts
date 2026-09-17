import type { ExpenseSummary } from '../api/types';

export interface CandidateFilter {
  /** 批次限定的经费项目；null 表示批次未限定项目 */
  projectId: number | null;
  showAllProjects: boolean;
  search: string;
}

/** 可加入批次的记录：排除“不报销/作废”。 */
export function selectableExpenses(items: readonly ExpenseSummary[]): ExpenseSummary[] {
  return items.filter((expense) => expense.status !== 'void');
}

function matchesSearch(expense: ExpenseSummary, keyword: string): boolean {
  if (!keyword) return true;
  return [expense.merchant, expense.summary, expense.invoice_no ?? '']
    .some((text) => text.toLowerCase().includes(keyword));
}

/** 本地过滤：按批次项目（可切换显示全部）与商家/摘要/发票号关键字。 */
export function filterBatchCandidates(items: readonly ExpenseSummary[], filter: CandidateFilter): ExpenseSummary[] {
  const keyword = filter.search.trim().toLowerCase();
  const limitProject = filter.projectId !== null && !filter.showAllProjects;
  return items.filter(
    (expense) => (!limitProject || expense.project_id === filter.projectId) && matchesSearch(expense, keyword),
  );
}
