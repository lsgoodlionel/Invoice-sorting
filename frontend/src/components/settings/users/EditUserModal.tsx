import { Modal, Stack, TextInput } from '@mantine/core';
import { useState, type FormEvent } from 'react';
import { useUpdateUser } from '../../../api/hooks/users';
import type { User, UserPatch, UserRole } from '../../../api/types';
import { DISPLAY_NAME_MAX_LENGTH, displayNameError } from '../../../lib/users';
import { FormError } from './FormError';
import { ModalActions } from './ModalActions';
import { RoleControl } from './RoleControl';

interface EditUserModalProps {
  user: User;
  /** 正在编辑当前登录的账户 */
  isSelf: boolean;
  onClose: () => void;
}

/** 只提交变化的字段。 */
function changedFields(user: User, displayName: string, role: UserRole): UserPatch {
  return {
    ...(displayName !== user.display_name ? { display_name: displayName } : {}),
    ...(role !== user.role ? { role } : {}),
  };
}

export function EditUserModal({ user, isSelf, onClose }: EditUserModalProps) {
  const update = useUpdateUser();
  const [displayName, setDisplayName] = useState(user.display_name);
  const [role, setRole] = useState<UserRole>(user.role);
  const trimmed = displayName.trim();
  const nameError = displayNameError(displayName, { required: true });
  const patch = changedFields(user, trimmed, role);
  const canSubmit = Boolean(trimmed) && !nameError && Object.keys(patch).length > 0;

  const changed = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    if (update.error) update.reset();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || update.isPending) return;
    update.mutate({ id: user.id, patch }, { onSuccess: onClose });
  };

  return (
    <Modal opened onClose={onClose} title={`编辑用户：${user.username}`}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <TextInput
            label="姓名"
            maxLength={DISPLAY_NAME_MAX_LENGTH}
            data-autofocus
            value={displayName}
            error={nameError}
            onChange={(event) => changed(setDisplayName)(event.currentTarget.value)}
          />
          <RoleControl
            value={role}
            isDemoteLocked={isSelf && user.role === 'admin'}
            onChange={changed(setRole)}
          />
          <FormError error={update.error} />
          <ModalActions submitLabel="保存" isSubmitting={update.isPending} canSubmit={canSubmit} onCancel={onClose} />
        </Stack>
      </form>
    </Modal>
  );
}
