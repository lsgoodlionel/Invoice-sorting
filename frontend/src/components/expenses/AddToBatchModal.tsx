import { Alert, Button, Group, Modal, Radio, Select, Stack, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useEffect, useState } from 'react';
import { useBatchItems, useBatchList, useCreateBatch } from '../../api/hooks/batches';
import { ApiError } from '../../api/client';

interface AddToBatchModalProps {
  opened: boolean;
  expenseIds: readonly number[];
  onClose: () => void;
  onDone: () => void;
}

type Mode = 'existing' | 'new';
const CONFLICT_STATUS = 409;

export function AddToBatchModal({ opened, expenseIds, onClose, onDone }: AddToBatchModalProps) {
  const { data: drafts = [] } = useBatchList('draft');
  const [mode, setMode] = useState<Mode>('existing');
  const [batchId, setBatchId] = useState<number | null>(null);
  const [newName, setNewName] = useState('');
  const [conflict, setConflict] = useState<{ batchId: number; message: string } | null>(null);
  const createBatch = useCreateBatch();
  const changeItems = useBatchItems();

  useEffect(() => {
    if (!opened) return;
    setConflict(null);
    setMode(drafts.length ? 'existing' : 'new');
  }, [opened, drafts.length]);

  const addItems = (targetId: number, force: boolean) => {
    changeItems.mutate(
      { id: targetId, change: { add: [...expenseIds], force } },
      {
        onSuccess: (detail) => {
          notifications.show({ color: 'ink', message: `已加入批次「${detail.name}」` });
          setConflict(null);
          onDone();
        },
        onError: (error) => {
          if (error instanceof ApiError && error.status === CONFLICT_STATUS) {
            setConflict({ batchId: targetId, message: error.message });
          }
        },
      },
    );
  };

  const submit = async () => {
    if (mode === 'existing' && batchId !== null) return addItems(batchId, false);
    if (mode === 'new' && newName.trim()) {
      const created = await createBatch.mutateAsync({ name: newName.trim() });
      setMode('existing');
      setBatchId(created.id);
      addItems(created.id, false);
    }
  };

  const canSubmit = mode === 'existing' ? batchId !== null : newName.trim() !== '';
  const isBusy = createBatch.isPending || changeItems.isPending;

  return (
    <Modal opened={opened} onClose={onClose} title={`加入批次（${expenseIds.length} 条）`}>
      <Stack gap="sm">
        <Radio.Group value={mode} onChange={(value) => setMode(value as Mode)}>
          <Group gap="lg">
            <Radio value="existing" label="已有草稿批次" disabled={drafts.length === 0} />
            <Radio value="new" label="新建批次" />
          </Group>
        </Radio.Group>
        {mode === 'existing' ? (
          <Select
            label="选择批次"
            data={drafts.map((batch) => ({ value: String(batch.id), label: `${batch.name}（${batch.item_count} 条）` }))}
            value={batchId === null ? null : String(batchId)}
            onChange={(value) => setBatchId(value === null ? null : Number(value))}
          />
        ) : (
          <TextInput label="批次名称" placeholder="如 2026-09 科研A 第1批" value={newName} onChange={(e) => setNewName(e.currentTarget.value)} />
        )}
        {conflict && (
          <Alert color="orange" title="需要确认">
            {conflict.message}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>取消</Button>
          {conflict ? (
            <Button variant="filled" color="orange" loading={isBusy} onClick={() => addItems(conflict.batchId, true)}>
              仍然加入
            </Button>
          ) : (
            <Button variant="filled" disabled={!canSubmit} loading={isBusy} onClick={() => void submit().catch(() => undefined)}>
              加入
            </Button>
          )}
        </Group>
      </Stack>
    </Modal>
  );
}
