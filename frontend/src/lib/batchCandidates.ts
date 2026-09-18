import type { DateBasis, ExpenseQuery, ExpenseStatus, ExpenseSummary } from '../api/types';
import { resolvePeriod, type Period } from './period';

/** 凭证快捷切换：全部 / 只看缺凭证（服务端 missing=true）/ 只看凭证齐全（前端 missing_count=0） */
export type EvidenceFilter = 'all' | 'missing' | 'complete';

/** 未分批记录可能处于的状态（未分批一般不会是已外发/已报销）。 */
export const CANDIDATE_STATUSES: readonly ExpenseStatus[] = ['spent', 'invoiced', 'complete'];

export interface CandidateFilters {
  period: Period;
  dateBasis: DateBasis;
  categoryId: number | null;
  /** 手动选择的经费项目；选择后优先于批次默认项目 */
  projectId: number | null;
  /** 批次限定了项目时，是否显示全部项目 */
  showAllProjects: boolean;
  statuses: readonly ExpenseStatus[];
  evidence: EvidenceFilter;
  search: string;
}

export const DEFAULT_CANDIDATE_FILTERS: CandidateFilters = {
  period: { preset: 'all' },
  dateBasis: 'spent',
  categoryId: null,
  projectId: null,
  showAllProjects: false,
  statuses: [],
  evidence: 'all',
  search: '',
};

/** 服务端查询中除 unbatched/page_size 外的部分。 */
export type CandidateQuery = Omit<ExpenseQuery, 'unbatched' | 'page' | 'page_size'>;

/** 可加入批次的记录：排除“不报销/作废”。 */
export function selectableExpenses(items: readonly ExpenseSummary[]): ExpenseSummary[] {
  return items.filter((expense) => expense.status !== 'void');
}

/** 实际用于查询的项目：手动选择 > 批次默认项目（未打开“显示全部项目”时）> 不限。 */
export function effectiveProjectId(filters: CandidateFilters, batchProjectId: number | null): number | null {
  if (filters.projectId !== null) return filters.projectId;
  return filters.showAllProjects ? null : batchProjectId;
}

/** 由弹窗筛选生成服务端查询参数（日期、分类、项目、状态、缺凭证）。 */
export function buildCandidateQuery(
  filters: CandidateFilters,
  batchProjectId: number | null,
  now: Date = new Date(),
): CandidateQuery {
  const range = resolvePeriod(filters.period, now);
  const hasRange = range.start !== undefined || range.end !== undefined;
  const projectId = effectiveProjectId(filters, batchProjectId);
  return {
    ...(range.start ? { start: range.start } : {}),
    ...(range.end ? { end: range.end } : {}),
    ...(hasRange ? { date_basis: filters.dateBasis } : {}),
    ...(filters.categoryId !== null ? { category_id: filters.categoryId } : {}),
    ...(projectId !== null ? { project_id: projectId } : {}),
    ...(filters.statuses.length > 0 ? { status: [...filters.statuses] } : {}),
    ...(filters.evidence === 'missing' ? { missing: true } : {}),
  };
}

function matchesSearch(expense: ExpenseSummary, keyword: string): boolean {
  if (!keyword) return true;
  return [expense.merchant, expense.summary, expense.invoice_no ?? '']
    .some((text) => text.toLowerCase().includes(keyword));
}

/** 本地过滤：排除作废、“只看凭证齐全”、商家/摘要/发票号关键字。 */
export function filterBatchCandidates(
  items: readonly ExpenseSummary[],
  filters: Pick<CandidateFilters, 'evidence' | 'search'>,
): ExpenseSummary[] {
  const keyword = filters.search.trim().toLowerCase();
  const onlyComplete = filters.evidence === 'complete';
  return selectableExpenses(items).filter(
    (expense) => (!onlyComplete || expense.missing_count === 0) && matchesSearch(expense, keyword),
  );
}

/** 是否有用户主动设置的筛选（批次默认项目限定不算）。 */
export function hasActiveFilters(filters: CandidateFilters): boolean {
  return (
    filters.period.preset !== 'all' ||
    filters.categoryId !== null ||
    filters.projectId !== null ||
    filters.statuses.length > 0 ||
    filters.evidence !== 'all' ||
    filters.search.trim() !== ''
  );
}
