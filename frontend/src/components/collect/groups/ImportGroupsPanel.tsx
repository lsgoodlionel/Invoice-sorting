import { Button, Group, Stack, Text } from '@mantine/core';
import { useReducer, useState } from 'react';
import type { ImportConfirmInput, ImportSession } from '../../../api/types';
import { buildConfirmInput, groupTitle, importGroupsReducer, initImportGroups, tallyGroups } from '../../../lib/importGroups';
import { GroupCard } from './GroupCard';
import { GroupTallyText } from './GroupTallyText';
import { MoveFileModal } from './MoveFileModal';

interface ImportGroupsPanelProps {
  session: ImportSession;
  onConfirm: (input: ImportConfirmInput) => void;
  isSubmitting: boolean;
}

/** 导入确认表：按凭证组展示，可改操作、移动/拆分文件、改类型，最后一次提交。 */
export function ImportGroupsPanel({ session, onConfirm, isSubmitting }: ImportGroupsPanelProps) {
  const [state, dispatch] = useReducer(importGroupsReducer, session, initImportGroups);
  const [movingId, setMovingId] = useState<number | null>(null);
  const tally = tallyGroups(state);
  const movingGroupIndex = state.groups.findIndex((group) => movingId !== null && group.attachmentIds.includes(movingId));
  const moveTargets = state.groups
    .map((group, index) => ({ value: group.groupId, label: groupTitle(state, group, index) }))
    .filter((_, index) => index !== movingGroupIndex);

  return (
    <Stack gap="sm">
      <GroupTallyText tally={tally} />
      {state.groups.map((group, index) => (
        <GroupCard key={group.groupId} state={state} group={group} index={index} dispatch={dispatch} onRequestMove={setMovingId} />
      ))}
      <Group justify="flex-end" gap="sm">
        {tally.invalid > 0 && <Text size="sm" c="red">{tally.invalid} 组需要处理后才能确认</Text>}
        <Button variant="filled" size="md" loading={isSubmitting} disabled={tally.invalid > 0} onClick={() => onConfirm(buildConfirmInput(state))}>
          全部确认
        </Button>
      </Group>
      <MoveFileModal
        attachment={movingId === null ? null : (state.attachments[movingId] ?? null)}
        targets={moveTargets}
        onMove={(targetGroupId) => movingId !== null && dispatch({ type: 'moveAttachment', attachmentId: movingId, targetGroupId })}
        onClose={() => setMovingId(null)}
      />
    </Stack>
  );
}
