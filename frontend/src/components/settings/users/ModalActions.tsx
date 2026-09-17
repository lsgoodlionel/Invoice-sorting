import { Button, Group } from '@mantine/core';

interface ModalActionsProps {
  submitLabel: string;
  isSubmitting: boolean;
  canSubmit: boolean;
  onCancel: () => void;
}

/** 弹窗底部：取消 + 提交（表单 submit）。 */
export function ModalActions({ submitLabel, isSubmitting, canSubmit, onCancel }: ModalActionsProps) {
  return (
    <Group justify="flex-end">
      <Button variant="subtle" onClick={onCancel}>取消</Button>
      <Button type="submit" variant="filled" loading={isSubmitting} disabled={!canSubmit}>{submitLabel}</Button>
    </Group>
  );
}
