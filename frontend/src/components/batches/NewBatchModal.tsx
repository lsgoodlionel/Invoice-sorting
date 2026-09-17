import { Button, Group, Modal, Stack, Textarea, TextInput } from '@mantine/core';
import { useEffect, useState } from 'react';
import { useCreateBatch } from '../../api/hooks/batches';
import { ProjectSelect } from '../ProjectSelect';

interface NewBatchModalProps {
  opened: boolean;
  onClose: () => void;
  onCreated: (id: number) => void;
}

export function NewBatchModal({ opened, onClose, onCreated }: NewBatchModalProps) {
  const [name, setName] = useState('');
  const [projectId, setProjectId] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const create = useCreateBatch();

  useEffect(() => {
    if (!opened) return;
    setName('');
    setProjectId(null);
    setNote('');
  }, [opened]);

  const submit = () =>
    create.mutate(
      { name: name.trim(), project_id: projectId, note },
      { onSuccess: (batch) => { onClose(); onCreated(batch.id); } },
    );

  return (
    <Modal opened={opened} onClose={onClose} title="新建批次">
      <Stack gap="sm">
        <TextInput label="名称" placeholder="如 2026-09 科研A 第1批" required value={name} onChange={(e) => setName(e.currentTarget.value)} data-autofocus />
        <ProjectSelect label="经费项目" clearable value={projectId} onChange={setProjectId} />
        <Textarea label="备注" autosize minRows={2} value={note} onChange={(e) => setNote(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>取消</Button>
          <Button variant="filled" disabled={!name.trim()} loading={create.isPending} onClick={submit}>创建</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
