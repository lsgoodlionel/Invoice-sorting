import { ActionIcon, Group, Image, Menu, Select, Stack, Text, Tooltip } from '@mantine/core';
import { IconDots } from '@tabler/icons-react';
import { attachmentsApi } from '../../../api/hooks/attachments';
import type { Attachment, AttachmentKind } from '../../../api/types';
import { attachmentFacts } from '../../../lib/evidence';
import { ATTACHMENT_KIND_OPTIONS } from '../../../lib/status';

interface GroupFileCardProps {
  attachment: Attachment;
  kind: AttachmentKind;
  canMove: boolean;
  canSplit: boolean;
  onKindChange: (kind: AttachmentKind) => void;
  onMove: () => void;
  onSplit: () => void;
}

const THUMB_SIZE = 56;
const CARD_WIDTH = 132;

function FactsLabel({ attachment }: { attachment: Attachment }) {
  const facts = attachmentFacts(attachment);
  return (
    <Stack gap={0}>
      <Text size="xs" fw={600}>{attachment.original_name}</Text>
      {facts.length === 0 && <Text size="xs">未识别内容</Text>}
      {facts.map((fact) => (
        <Text key={fact.label} size="xs" className="num">{fact.label}：{fact.value}</Text>
      ))}
    </Stack>
  );
}

/** 组内文件小卡片：缩略图（悬停看识别摘要）、类型、移动/拆分菜单。 */
export function GroupFileCard({ attachment, kind, canMove, canSplit, onKindChange, onMove, onSplit }: GroupFileCardProps) {
  const name = attachment.original_name;
  return (
    <Stack gap={4} w={CARD_WIDTH} className="group-file" data-testid={`group-file-${attachment.id}`}>
      <Group gap={4} wrap="nowrap" align="flex-start">
        <Tooltip label={<FactsLabel attachment={attachment} />} multiline w={240} withArrow>
          <a href={attachment.url} target="_blank" rel="noreferrer" aria-label={`打开 ${name}`}>
            <Image src={attachmentsApi.thumbnailUrl(attachment.id)} w={THUMB_SIZE} h={THUMB_SIZE} fit="cover" radius="xs" alt="" />
          </a>
        </Tooltip>
        <Menu position="bottom-start" withinPortal>
          <Menu.Target>
            <ActionIcon size="sm" variant="subtle" aria-label={`文件操作 ${name}`}><IconDots size={14} /></ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item disabled={!canMove} onClick={onMove}>移到其他组…</Menu.Item>
            <Menu.Item disabled={!canSplit} onClick={onSplit}>拆为单独一组</Menu.Item>
          </Menu.Dropdown>
        </Menu>
      </Group>
      <Select
        size="xs"
        aria-label={`类型 ${name}`}
        data={ATTACHMENT_KIND_OPTIONS}
        value={kind}
        allowDeselect={false}
        onChange={(value) => value && onKindChange(value as AttachmentKind)}
      />
      <Text size="xs" c="dimmed" truncate title={name}>{name}</Text>
    </Stack>
  );
}
