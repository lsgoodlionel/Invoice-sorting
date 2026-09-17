import { notifications } from '@mantine/notifications';
import { useCallback, useState } from 'react';
import { ApiError } from '../../api/client';
import { useBatchItems } from '../../api/hooks/batches';
import type { BatchDetail } from '../../api/types';

const CONFLICT_STATUS = 409;

export interface BatchAddConflict {
  batchId: number;
  expenseIds: readonly number[];
  /** 后端返回的中文说明（缺必需凭证 / 项目不一致等） */
  message: string;
}

/**
 * 把记录加入批次，统一处理 409：保存冲突说明，由调用方展示并通过 confirm() 以 force=true 重试。
 * 其他错误仍走全局错误提示。
 */
export function useAddToBatch(onAdded: (detail: BatchDetail) => void) {
  const changeItems = useBatchItems();
  const [conflict, setConflict] = useState<BatchAddConflict | null>(null);
  const reset = useCallback(() => setConflict(null), []);

  const add = (batchId: number, expenseIds: readonly number[], force = false) =>
    changeItems.mutate(
      { id: batchId, change: { add: [...expenseIds], force } },
      {
        onSuccess: (detail) => {
          notifications.show({ color: 'ink', message: `已加入批次「${detail.name}」` });
          setConflict(null);
          onAdded(detail);
        },
        onError: (error) => {
          if (error instanceof ApiError && error.status === CONFLICT_STATUS) {
            setConflict({ batchId, expenseIds, message: error.message });
          }
        },
      },
    );

  const confirm = () => {
    if (conflict) add(conflict.batchId, conflict.expenseIds, true);
  };

  return { add, confirm, conflict, reset, isPending: changeItems.isPending };
}
