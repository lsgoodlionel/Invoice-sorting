import { ActionIcon, Badge, Button, Group, Popover, Stack, Text, TextInput, Tooltip } from '@mantine/core';
import { IconCheck, IconMinus, IconX } from '@tabler/icons-react';
import { useState } from 'react';
import type { Attachment, AttachmentKind, ChecklistItem } from '../api/types';
import { ACCEPTED_FILE_TYPES, UploadDrop } from './UploadDrop';

interface ChecklistPanelProps {
  items: readonly ChecklistItem[];
  attachments: readonly Attachment[];
  onUpload: (kind: AttachmentKind, files: File[]) => void;
  onSetState: (itemId: number, state: 'missing' | 'not_needed', reason?: string) => void;
  isBusy?: boolean;
}

function StateIcon({ state }: { state: ChecklistItem['state'] }) {
  if (state === 'present') return <IconCheck size={16} color="var(--mantine-color-green-7)" aria-label="已有" />;
  if (state === 'not_needed') return <IconMinus size={16} color="var(--mantine-color-gray-6)" aria-label="不需要" />;
  return <IconX size={16} color="var(--mantine-color-red-7)" aria-label="缺少" />;
}

function NotNeededButton({ onConfirm }: { onConfirm: (reason: string) => void }) {
  const [opened, setOpened] = useState(false);
  const [reason, setReason] = useState('');
  return (
    <Popover opened={opened} onChange={setOpened} position="bottom-end" withArrow trapFocus>
      <Popover.Target>
        <Button size="compact-xs" variant="subtle" onClick={() => setOpened((value) => !value)}>
          不需要
        </Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap={6}>
          <TextInput size="xs" label="原因（可选）" value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
          <Button
            size="compact-xs"
            variant="filled"
            onClick={() => {
              setOpened(false);
              onConfirm(reason.trim());
            }}
          >
            确认不需要
          </Button>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}

function ChecklistRow({ item, attachments, onUpload, onSetState, isBusy }: Omit<ChecklistPanelProps, 'items'> & { item: ChecklistItem }) {
  const linked = attachments.filter((attachment) => attachment.kind === item.attachment_kind);
  return (
    <Group className="checklist-row" data-state={item.state} gap="sm" wrap="nowrap" align="flex-start" data-testid={`checklist-${item.id}`}>
      <StateIcon state={item.state} />
      <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
        <Group gap={6} wrap="nowrap">
          <Text size="sm" fw={500}>{item.kind_label}</Text>
          {item.level === 'suggested' && <Badge size="xs" variant="outline" color="gray">建议</Badge>}
        </Group>
        {item.hint && <Text size="xs" c="dimmed">{item.hint}</Text>}
        {item.state === 'present' && <Text size="xs" truncate>{linked.map((a) => a.original_name).join('、')}</Text>}
        {item.state === 'not_needed' && item.reason && <Text size="xs" c="dimmed">原因：{item.reason}</Text>}
      </Stack>
      {item.state === 'missing' && (
        <Group gap={4} wrap="nowrap">
          <UploadDrop w={150} accept={ACCEPTED_FILE_TYPES} loading={isBusy} onFiles={(files) => onUpload(item.attachment_kind, files)} />
          <NotNeededButton onConfirm={(reason) => onSetState(item.id, 'not_needed', reason || undefined)} />
        </Group>
      )}
      {item.state === 'not_needed' && (
        <Tooltip label="恢复为需要">
          <ActionIcon variant="subtle" aria-label="恢复" onClick={() => onSetState(item.id, 'missing')}>
            <Text size="xs">恢复</Text>
          </ActionIcon>
        </Tooltip>
      )}
    </Group>
  );
}

/** 凭证清单：缺项行内补传或标记不需要。 */
export function ChecklistPanel({ items, ...rest }: ChecklistPanelProps) {
  if (items.length === 0) {
    return <Text size="sm" c="dimmed">该分类没有凭证要求。</Text>;
  }
  return (
    <Stack gap={0}>
      {items.map((item) => (
        <ChecklistRow key={item.id} item={item} {...rest} />
      ))}
    </Stack>
  );
}
