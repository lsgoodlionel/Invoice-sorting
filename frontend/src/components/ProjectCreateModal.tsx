import { Button, Group, Modal, Stack, TextInput } from '@mantine/core';
import { useEffect, useState } from 'react';
import { useSaveProject } from '../api/hooks/settings';
import type { Project } from '../api/types';

interface ProjectCreateModalProps {
  opened: boolean;
  onClose: () => void;
  onCreated: (project: Project) => void;
}

interface Draft {
  code: string;
  name: string;
  owner: string;
}

const emptyDraft = (): Draft => ({ code: '', name: '', owner: '' });

/**
 * 就地新建经费项目的小弹窗：名称必填，经费号与负责人可选。
 * 不使用 form：弹窗常嵌在其他表单内，React 事件会穿过 portal 冒泡触发外层提交。
 */
export function ProjectCreateModal({ opened, onClose, onCreated }: ProjectCreateModalProps) {
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const save = useSaveProject();

  useEffect(() => {
    if (opened) setDraft(emptyDraft());
  }, [opened]);

  const patch = (next: Partial<Draft>) => setDraft((current) => ({ ...current, ...next }));
  const isValid = draft.name.trim() !== '';

  const submit = () => {
    if (!isValid) return;
    const input = { code: draft.code.trim(), name: draft.name.trim(), owner: draft.owner.trim() };
    save.mutate(
      { id: null, input },
      {
        onSuccess: (project) => {
          onClose();
          onCreated(project);
        },
      },
    );
  };

  return (
    <Modal opened={opened} onClose={onClose} title="新建经费项目" size="sm">
      <Stack gap="sm">
        <TextInput label="名称" required data-autofocus value={draft.name} onChange={(e) => patch({ name: e.currentTarget.value })} />
        <TextInput label="经费号" placeholder="可选" value={draft.code} onChange={(e) => patch({ code: e.currentTarget.value })} />
        <TextInput label="负责人" placeholder="可选" value={draft.owner} onChange={(e) => patch({ owner: e.currentTarget.value })} />
        <Group justify="flex-end" mt="xs">
          <Button variant="subtle" onClick={onClose}>取消</Button>
          <Button variant="filled" disabled={!isValid} loading={save.isPending} onClick={submit}>创建并选中</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
