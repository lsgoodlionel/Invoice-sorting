import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { decodeExpenseFilters, encodeExpenseFilters, type ExpenseFilters } from '../../lib/expenseFilters';

/** 清单筛选条件与 URL 查询参数双向同步。 */
export function useExpenseFilters(): [ExpenseFilters, (patch: Partial<ExpenseFilters>) => void] {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => decodeExpenseFilters(params), [params]);
  const update = useCallback(
    (patch: Partial<ExpenseFilters>) => {
      setParams((current) => encodeExpenseFilters({ ...decodeExpenseFilters(current), ...patch }), { replace: true });
    },
    [setParams],
  );
  return [filters, update];
}
