import { Stack, Text } from '@mantine/core';
import { useState } from 'react';
import { useUnassignedAttachments } from '../../../api/hooks/attachments';
import type { Attachment, CreateExpensesSkip } from '../../../api/types';
import { isInvoiceAttachment, pruneSelection, selectedInvoiceIds, toggleAllIds, toggleId } from '../../../lib/unassigned';
import { AssignModal } from './AssignModal';
import { CreateSkippedAlert } from './CreateSkippedAlert';
import { PreviewModal } from './PreviewModal';
import { UnassignedHeader } from './UnassignedHeader';
import { UnassignedBulkBar } from './UnassignedBulkBar';
import { UnassignedTable } from './UnassignedTable';
import { useUnassignedActions } from './useUnassignedActions';

interface UnassignedSectionProps {
  /** 同屏已有 filled 主按钮（如导入确认表）时，本区主按钮改用 light 样式 */
  hasOtherPrimary: boolean;
}

export function UnassignedSection({ hasOtherPrimary }: UnassignedSectionProps) {
  const { data = [] } = useUnassignedAttachments();
  const [rawSelected, setSelected] = useState<number[]>([]);
  const [assignIds, setAssignIds] = useState<number[] | null>(null);
  const [preview, setPreview] = useState<Attachment | null>(null);
  const [skipped, setSkipped] = useState<CreateExpensesSkip[]>([]);
  const clearSelection = () => setSelected([]);
  const actions = useUnassignedActions({ onCreated: (result) => setSkipped(result.skipped), onDone: clearSelection });

  const selected = pruneSelection(rawSelected, data);
  const selectedInvoices = selectedInvoiceIds(selected, data);
  const allInvoiceIds = data.filter(isInvoiceAttachment).map((item) => item.id);

  return (
    <Stack gap="xs" id="unassigned">
      <UnassignedHeader
        total={data.length}
        invoiceCount={allInvoiceIds.length}
        isCreating={actions.isCreating}
        onCreateAll={() => actions.createExpenses(allInvoiceIds)}
      />
      <CreateSkippedAlert skipped={skipped} onClose={() => setSkipped([])} />
      {data.length === 0 ? (
        <Text size="sm" c="dimmed">没有待归属的附件。订单截图、支付记录等非发票文件导入后会出现在这里。</Text>
      ) : (
        <UnassignedTable
          items={data}
          selectedIds={selected}
          onToggle={(id) => setSelected(toggleId(selected, id))}
          onToggleAll={(checked) => setSelected(toggleAllIds(data, checked))}
          onAssign={(id) => setAssignIds([id])}
          onPreview={setPreview}
        />
      )}
      {selected.length > 0 && (
        <UnassignedBulkBar
          count={selected.length}
          invoiceCount={selectedInvoices.length}
          primaryVariant={hasOtherPrimary ? 'light' : 'filled'}
          isCreating={actions.isCreating}
          isReparsing={actions.isReparsing}
          isDeleting={actions.isDeleting}
          onCreate={() => actions.createExpenses(selectedInvoices)}
          onAssign={() => setAssignIds(selected)}
          onReparse={() => actions.reparseInvoices(selectedInvoices)}
          onDelete={() => actions.confirmDelete(selected)}
          onClear={clearSelection}
        />
      )}
      <AssignModal ids={assignIds} onClose={() => setAssignIds(null)} onAssigned={clearSelection} />
      <PreviewModal attachment={preview} onClose={() => setPreview(null)} />
    </Stack>
  );
}
