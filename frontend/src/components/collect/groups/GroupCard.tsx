import { Box, Group, Paper, Stack, Text } from '@mantine/core';
import type { Dispatch } from 'react';
import {
  effectiveKind,
  groupAttachments,
  groupProblems,
  groupTitle,
  type GroupDraft,
  type ImportGroupsAction,
  type ImportGroupsState,
} from '../../../lib/importGroups';
import { GroupFieldsForm } from './GroupFieldsForm';
import { GroupFileCard } from './GroupFileCard';
import { GroupNotes } from './GroupNotes';
import { GroupOperation } from './GroupOperation';

interface GroupCardProps {
  state: ImportGroupsState;
  group: GroupDraft;
  index: number;
  dispatch: Dispatch<ImportGroupsAction>;
  onRequestMove: (attachmentId: number) => void;
}

const OPERATION_WIDTH = 260;

export function GroupCard({ state, group, index, dispatch, onRequestMove }: GroupCardProps) {
  const { groupId } = group;
  const attachments = groupAttachments(state, group);
  const problems = groupProblems(state, group);
  const canMove = state.groups.length > 1;
  const canSplit = attachments.length > 1;
  return (
    <Paper
      className="import-group"
      data-invalid={problems.length > 0 || undefined}
      data-skipped={group.operation.type === 'skip' || undefined}
      data-testid={`import-group-${groupId}`}
      p="sm"
      radius={0}
    >
      <Stack gap="xs">
        <Group gap="xs">
          <Text size="sm" fw={600}>{groupTitle(state, group, index)}</Text>
          <Text size="xs" c="dimmed">{attachments.length} 个文件</Text>
        </Group>
        <Group align="flex-start" gap="md" wrap="nowrap" className="import-group-body">
          <Group gap="xs" align="flex-start" className="import-group-files">
            {attachments.map((attachment) => (
              <GroupFileCard
                key={attachment.id}
                attachment={attachment}
                kind={effectiveKind(state, attachment.id) ?? attachment.kind}
                canMove={canMove}
                canSplit={canSplit}
                onKindChange={(kind) => dispatch({ type: 'setKind', attachmentId: attachment.id, kind })}
                onMove={() => onRequestMove(attachment.id)}
                onSplit={() => dispatch({ type: 'splitAttachment', attachmentId: attachment.id })}
              />
            ))}
          </Group>
          <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
            <GroupFieldsForm group={group} onChange={(patch) => dispatch({ type: 'updateFields', groupId, patch })} />
            <GroupNotes linkReasons={group.linkReasons} warnings={group.warnings} problems={problems} />
          </Stack>
          <Box w={OPERATION_WIDTH} style={{ flexShrink: 0 }}>
            <GroupOperation group={group} onChange={(operation) => dispatch({ type: 'setOperation', groupId, operation })} />
          </Box>
        </Group>
      </Stack>
    </Paper>
  );
}
