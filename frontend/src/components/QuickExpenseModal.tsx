import { Button, Group, Modal, Stack, TextInput } from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { notifications } from '@mantine/notifications';
import { useEffect, useState } from 'react';
import { useCreateExpense } from '../api/hooks/expenses';
import { todayInShanghai } from '../lib/period';
import { CategorySelect } from './CategorySelect';
import { MoneyInput } from './MoneyInput';
import { ProjectSelect } from './ProjectSelect';

interface QuickExpenseModalProps {
  opened: boolean;
  onClose: () => void;
  onCreated?: (id: number) => void;
}

interface Draft {
  spentOn: string | null;
  cents: number | null;
  merchant: string;
  categoryId: number | null;
  projectId: number | null;
}

const emptyDraft = (): Draft => ({ spentOn: todayInShanghai(), cents: null, merchant: '', categoryId: null, projectId: null });

export function QuickExpenseModal({ opened, onClose, onCreated }: QuickExpenseModalProps) {
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const create = useCreateExpense();

  useEffect(() => {
    if (opened) setDraft(emptyDraft());
  }, [opened]);

  const isValid = Boolean(draft.spentOn) && draft.cents !== null && draft.cents > 0 && draft.merchant.trim() !== '';
  const update = (patch: Partial<Draft>) => setDraft((current) => ({ ...current, ...patch }));

  const submit = () => {
    if (!isValid || draft.spentOn === null || draft.cents === null) return;
    create.mutate(
      {
        spent_on: draft.spentOn,
        amount_cents: draft.cents,
        merchant: draft.merchant.trim(),
        category_id: draft.categoryId,
        project_id: draft.projectId,
      },
      {
        onSuccess: (detail) => {
          notifications.show({ color: 'ink', message: `已记一笔：${detail.merchant}` });
          onClose();
          onCreated?.(detail.id);
        },
      },
    );
  };

  return (
    <Modal opened={opened} onClose={onClose} title="快速记一笔" size="sm">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <Stack gap="sm">
          <DateInput label="支出日期" valueFormat="YYYY-MM-DD" value={draft.spentOn} onChange={(v) => update({ spentOn: v })} required />
          <MoneyInput label="金额（元）" cents={draft.cents} onCentsChange={(cents) => update({ cents })} required data-autofocus />
          <TextInput label="商家" value={draft.merchant} onChange={(e) => update({ merchant: e.currentTarget.value })} required />
          <CategorySelect label="分类" value={draft.categoryId} onChange={(categoryId) => update({ categoryId })} clearable />
          <ProjectSelect label="经费项目" value={draft.projectId} onChange={(projectId) => update({ projectId })} clearable />
          <Group justify="flex-end" mt="xs">
            <Button variant="subtle" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" variant="filled" disabled={!isValid} loading={create.isPending}>
              保存为“已支出”
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
