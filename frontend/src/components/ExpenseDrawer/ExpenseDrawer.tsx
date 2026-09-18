import { Divider, Drawer, Group, Loader, Stack, Text } from '@mantine/core';
import type { ReactNode } from 'react';
import { useSetChecklistState } from '../../api/hooks/attachments';
import { useExpense, useUploadExpenseAttachments } from '../../api/hooks/expenses';
import type { ExpenseDetail } from '../../api/types';
import { formatCents } from '../../lib/money';
import { ChecklistPanel } from '../ChecklistPanel';
import { AttachmentList } from './AttachmentList';
import { DangerZone } from './DangerZone';
import { ExpenseFields } from './ExpenseFields';
import { InvoiceMeta } from './InvoiceMeta';
import { RouteHint } from './RouteHint';
import { StatusSection } from './StatusSection';
import { TimelineSection } from './TimelineSection';
import { AmountComposition, LodgingBanner } from './TravelInfo';

interface ExpenseDrawerProps {
  expenseId: number | null;
  onClose: () => void;
}

const DRAWER_WIDTH = 640;

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Stack gap="xs">
      <Divider label={<span className="section-label">{label}</span>} labelPosition="left" />
      {children}
    </Stack>
  );
}

function DrawerTitle({ expense }: { expense: ExpenseDetail }) {
  return (
    <Group justify="space-between" wrap="nowrap" w={DRAWER_WIDTH - 80}>
      <Text fw={600} truncate>
        {expense.merchant}
        {expense.summary && <Text span c="dimmed"> · {expense.summary}</Text>}
      </Text>
      <Stack gap={0} align="flex-end" style={{ flexShrink: 0 }}>
        <Text fw={700} size="lg" className="num">{formatCents(expense.amount_cents)}</Text>
        <AmountComposition amountCents={expense.amount_cents} attachments={expense.attachments} />
      </Stack>
    </Group>
  );
}

function DrawerBody({ expense, onClose }: { expense: ExpenseDetail; onClose: () => void }) {
  const upload = useUploadExpenseAttachments(expense.id);
  const setChecklist = useSetChecklistState();
  return (
    <Stack gap="lg" pb="xl">
      <LodgingBanner attachments={expense.attachments} />
      <StatusSection expense={expense} />
      <ExpenseFields expense={expense} />
      <InvoiceMeta expense={expense} />
      <Section label="凭证清单">
        <ChecklistPanel
          items={expense.checklist}
          attachments={expense.attachments}
          isBusy={upload.isPending}
          onUpload={(kind, files) => upload.mutate({ files, kind })}
          onSetState={(id, state, reason) => setChecklist.mutate({ id, state, reason })}
        />
        <RouteHint text={expense.route_hint} />
      </Section>
      <Section label={`附件 ${expense.attachments.length}`}>
        <AttachmentList attachments={expense.attachments} />
      </Section>
      <Section label="时间线">
        <TimelineSection events={expense.timeline} />
      </Section>
      <Section label="危险操作">
        <DangerZone expense={expense} onDeleted={onClose} />
      </Section>
    </Stack>
  );
}

export function ExpenseDrawer({ expenseId, onClose }: ExpenseDrawerProps) {
  const { data, isLoading } = useExpense(expenseId);
  const expense = data && data.id === expenseId ? data : null;
  return (
    <Drawer
      opened={expenseId !== null}
      onClose={onClose}
      position="right"
      size={DRAWER_WIDTH}
      closeOnEscape
      title={expense ? <DrawerTitle expense={expense} /> : '支出详情'}
      styles={{ content: { background: 'var(--paper-bg)' }, header: { background: 'var(--paper-bg)', borderBottom: '1px solid var(--paper-line)' } }}
    >
      {isLoading && <Loader size="sm" mt="md" />}
      {expense && <DrawerBody expense={expense} onClose={onClose} />}
    </Drawer>
  );
}
