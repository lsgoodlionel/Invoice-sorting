import { Text } from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import {
  useBulkDeleteAttachments,
  useCreateExpensesFromAttachments,
  useReparseAttachments,
} from '../../../api/hooks/attachments';
import type { CreateExpensesResult } from '../../../api/types';
import { summarizeCreateResult } from '../../../lib/unassigned';

interface ActionCallbacks {
  onCreated: (result: CreateExpensesResult) => void;
  onDone: () => void;
}

/** 待归属批量操作：生成记录、重新识别、删除（二次确认）。成功后由 hooks 刷新待归属/清单/dashboard。 */
export function useUnassignedActions({ onCreated, onDone }: ActionCallbacks) {
  const create = useCreateExpensesFromAttachments();
  const reparse = useReparseAttachments();
  const bulkDelete = useBulkDeleteAttachments();

  const createExpenses = (ids: readonly number[]) =>
    create.mutate(ids, {
      onSuccess: (result) => {
        notifications.show({ color: 'ink', title: '生成记录完成', message: summarizeCreateResult(result) });
        onCreated(result);
        onDone();
      },
    });

  const reparseInvoices = (ids: readonly number[]) =>
    reparse.mutate(ids, {
      onSuccess: (items) => {
        notifications.show({ color: 'ink', message: `已重新识别 ${items.length} 个` });
        onDone();
      },
    });

  const confirmDelete = (ids: readonly number[]) =>
    modals.openConfirmModal({
      title: `删除 ${ids.length} 个待归属附件`,
      children: <Text size="sm">所选文件将移入回收站，不会挂到任何记录。</Text>,
      labels: { confirm: `删除 ${ids.length} 个`, cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () =>
        bulkDelete.mutate(ids, {
          onSuccess: (result) => {
            notifications.show({ color: 'ink', message: `已删除 ${result.deleted} 个附件` });
            onDone();
          },
        }),
    });

  return {
    createExpenses,
    reparseInvoices,
    confirmDelete,
    isCreating: create.isPending,
    isReparsing: reparse.isPending,
    isDeleting: bulkDelete.isPending,
  };
}
