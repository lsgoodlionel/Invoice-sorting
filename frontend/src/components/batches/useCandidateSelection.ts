import { useCallback, useState } from 'react';

function toggleIds(ids: readonly number[], targets: readonly number[], checked: boolean): number[] {
  const rest = ids.filter((id) => !targets.includes(id));
  return checked ? [...rest, ...targets] : rest;
}

/**
 * 候选记录勾选：筛选结果变化（且新结果已加载完成）时，自动取消不在结果中的勾选，
 * 并记录本次取消的数量用于底部说明。
 */
export function useCandidateSelection(visibleIds: readonly number[], isSettled: boolean) {
  const [storedIds, setStoredIds] = useState<readonly number[]>([]);
  const [droppedCount, setDroppedCount] = useState(0);
  const visibleKey = visibleIds.join(',');
  const [seenKey, setSeenKey] = useState(visibleKey);

  // 渲染期间根据新结果调整状态（React 推荐的“随 props 调整 state”写法，避免 effect 闪烁）
  if (isSettled && visibleKey !== seenKey) {
    setSeenKey(visibleKey);
    const kept = storedIds.filter((id) => visibleIds.includes(id));
    if (kept.length !== storedIds.length) {
      setStoredIds(kept);
      setDroppedCount(storedIds.length - kept.length);
    }
  }

  const toggle = useCallback((ids: readonly number[], checked: boolean) => {
    setDroppedCount(0);
    setStoredIds((current) => toggleIds(current, ids, checked));
  }, []);

  const reset = useCallback(() => {
    setStoredIds([]);
    setDroppedCount(0);
  }, []);

  const selectedIds = storedIds.filter((id) => visibleIds.includes(id));
  return { selectedIds, droppedCount, toggle, reset };
}
