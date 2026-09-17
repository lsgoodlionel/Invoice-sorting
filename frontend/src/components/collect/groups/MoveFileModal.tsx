import { Button, Group, Modal, Select, Stack, Text } from '@mantine/core';
import { useEffect, useState } from 'react';
import type { Attachment } from '../../../api/types';

interface MoveFileModalProps {
  attachment: Attachment | null;
  targets: readonly { value: string; label: string }[];
  onMove: (groupId: string) => void;
  onClose: () => void;
}

export function MoveFileModal({ attachment, targets, onMove, onClose }: MoveFileModalProps) {
  const [target, setTarget] = useState<string | null>(null);
  useEffect(() => setTarget(null), [attachment]);
  const submit = () => {
    if (target === null) return;
    onMove(target);
    onClose();
  };
  return (
    <Modal opened={attachment !== null} onClose={onClose} title="移到其他组">
      <Stack gap="sm">
        <Text size="sm" truncate>{attachment?.original_name}</Text>
        <Select label="目标组" aria-label="目标组" placeholder="选择组" data={[...targets]} value={target} onChange={setTarget} />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>取消</Button>
          <Button variant="filled" disabled={target === null} onClick={submit}>移动</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
