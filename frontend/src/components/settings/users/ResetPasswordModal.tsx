import { Alert, Modal, Stack } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type FormEvent } from 'react';
import { useResetUserPassword } from '../../../api/hooks/users';
import type { User } from '../../../api/types';
import { isNewPasswordValid } from '../../../lib/password';
import { NewPasswordFields } from '../../auth/NewPasswordFields';
import { FormError } from './FormError';
import { ModalActions } from './ModalActions';

export function ResetPasswordModal({ user, onClose }: { user: User; onClose: () => void }) {
  const reset = useResetUserPassword();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const canSubmit = isNewPasswordValid(password, confirm);

  const changed = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    if (reset.error) reset.reset();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || reset.isPending) return;
    reset.mutate(
      { id: user.id, password },
      {
        onSuccess: () => {
          notifications.show({ color: 'ink', message: `已重置「${user.display_name}」的密码` });
          onClose();
        },
      },
    );
  };

  return (
    <Modal opened onClose={onClose} title={`重置密码：${user.display_name}`}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <Alert color="yellow" variant="light">该用户需使用新密码重新登录</Alert>
          <NewPasswordFields
            password={password}
            confirm={confirm}
            autoFocus
            onPasswordChange={changed(setPassword)}
            onConfirmChange={changed(setConfirm)}
          />
          <FormError error={reset.error} />
          <ModalActions submitLabel="重置密码" isSubmitting={reset.isPending} canSubmit={canSubmit} onCancel={onClose} />
        </Stack>
      </form>
    </Modal>
  );
}
