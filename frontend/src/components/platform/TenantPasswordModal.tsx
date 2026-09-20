import { Alert, Modal, Stack } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type FormEvent } from 'react';
import { useResetTenantMemberPassword } from '../../api/hooks/platformMembers';
import type { User } from '../../api/types';
import { isNewPasswordValid } from '../../lib/password';
import { NewPasswordFields } from '../auth/NewPasswordFields';
import { FormError } from '../settings/users/FormError';
import { ModalActions } from '../settings/users/ModalActions';

interface Props {
  slug: string;
  member: User;
  onClose: () => void;
}

/** 平台管理员为任意账套的成员重置密码；该成员全部会话立即失效。 */
export function TenantPasswordModal({ slug, member, onClose }: Props) {
  const reset = useResetTenantMemberPassword(slug);
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
      { id: member.id, password },
      {
        onSuccess: () => {
          notifications.show({ color: 'ink', message: `已重置「${member.display_name}」的密码` });
          onClose();
        },
      },
    );
  };

  return (
    <Modal opened onClose={onClose} title={`重置密码：${member.display_name}`}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <Alert color="yellow" variant="light">该成员需使用新密码重新登录</Alert>
          <NewPasswordFields
            password={password}
            confirm={confirm}
            onPasswordChange={changed(setPassword)}
            onConfirmChange={changed(setConfirm)}
            passwordLabel="新密码"
          />
          <FormError error={reset.error} />
          <ModalActions submitLabel="重置密码" isSubmitting={reset.isPending} canSubmit={canSubmit} onCancel={onClose} />
        </Stack>
      </form>
    </Modal>
  );
}
