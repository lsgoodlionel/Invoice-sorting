import { Alert, Button, Group, Radio, Stack, Text, TextInput } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useState } from 'react';
import type { ImportMode } from '../../../api/hooks/backup';

interface ImportConfirmFormProps {
  /** 覆盖模式需要一字不差输入的账套名称 */
  targetName: string;
  isSubmitting: boolean;
  error: string;
  onConfirm: (mode: ImportMode, confirmName: string) => void;
  onCancel: () => void;
}

function ReplaceWarning({ targetName, value, onChange }: { targetName: string; value: string; onChange: (value: string) => void }) {
  return (
    <Stack gap="xs" className="danger-zone">
      <Alert color="red" variant="light" icon={<IconAlertTriangle size={16} />} title="危险操作：当前账本将被整套替换">
        「{targetName}」现有的记录、附件、分类、批次都会被清空，换成搬迁包里的内容。执行前会先自动备份到 备份/ 目录，出错可以从备份恢复。
      </Alert>
      <TextInput
        label={`输入当前账套名称「${targetName}」以确认`}
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
        autoComplete="off"
      />
    </Stack>
  );
}

/** 选择导入模式并确认；覆盖模式必须输入正确账套名才能提交。 */
export function ImportConfirmForm({ targetName, isSubmitting, error, onConfirm, onCancel }: ImportConfirmFormProps) {
  const [mode, setMode] = useState<ImportMode>('merge');
  const [confirmName, setConfirmName] = useState('');
  const isReplace = mode === 'replace';
  const canSubmit = !isReplace || confirmName.trim() === targetName;

  return (
    <Stack gap="sm">
      <Radio.Group label="导入方式" value={mode} onChange={(value) => setMode(value as ImportMode)}>
        <Stack gap="xs" mt={6}>
          <Radio value="merge" label="合并到现有账本" description="只新增，不修改已有记录；重复的自动跳过" />
          <Radio value="replace" color="red" label="清空后整套覆盖" description="以搬迁包为准，替换当前账本的全部内容" />
        </Stack>
      </Radio.Group>
      {isReplace && <ReplaceWarning targetName={targetName} value={confirmName} onChange={setConfirmName} />}
      {error && <Alert color="red" variant="light">{error}</Alert>}
      <Group gap="sm">
        <Button
          variant="filled"
          color={isReplace ? 'red' : undefined}
          disabled={!canSubmit}
          loading={isSubmitting}
          onClick={() => onConfirm(mode, confirmName.trim())}
        >
          {isReplace ? '清空并覆盖' : '确认导入'}
        </Button>
        <Button variant="subtle" disabled={isSubmitting} onClick={onCancel}>放弃导入</Button>
      </Group>
      {isReplace && !canSubmit && <Text size="xs" c="dimmed">账套名称输入一致后才能执行覆盖。</Text>}
    </Stack>
  );
}
