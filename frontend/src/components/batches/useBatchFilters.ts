import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { decodeBatchFilters, encodeBatchFilters, type BatchFilters } from '../../lib/batchFilters';

/** 批次列表筛选与 URL 查询参数（batch_*）双向同步，保留 id 等其他参数。 */
export function useBatchFilters(): [BatchFilters, (patch: Partial<BatchFilters>) => void] {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => decodeBatchFilters(params), [params]);
  const update = useCallback(
    (patch: Partial<BatchFilters>) => {
      setParams((current) => encodeBatchFilters(current, { ...decodeBatchFilters(current), ...patch }), { replace: true });
    },
    [setParams],
  );
  return [filters, update];
}
