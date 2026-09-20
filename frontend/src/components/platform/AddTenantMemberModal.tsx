import { Modal, Stack, Text, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type FormEvent } from 'react';
import { useAddTenantMember } from '../../api/hooks/platformMembers';
import type { PlatformMemberInput, UserRole } from '../../api/types';
import { isNewPasswordValid } from '../../lib/password';
import { isUsernameValid, usernameError } from '../../lib/users';
import { NewPasswordFields } from '../auth/NewPasswordFields';
import { FormError } from '../settings/users/FormError';
import { ModalActions } from '../settings/users/ModalActions';
import { RoleControl } from '../settings/users/RoleControl';

const INTRO = '用户名已存在时会把该账号加入本账套，不改它的密码。';

interface AddForm {
  username: string;
  displayName: string;
  role: UserRole;
  password: string;
  confirm: string;
}

const EMPTY: AddForm = { username: '', displayName: '', role: 'member', password: '', confirm: '' };

function toPayload(form: AddForm): PlatformMemberInput {
  const displayName = form.displayName.trim();
  return {
    username: form.username.trim(),
    ...(displayName ? { display_name: displayName } : {}),
    ...(form.password ? { password: form.password } : {}),
    role: form.role,
  };
}

/** 为指定账套添加成员；密码留空表示对方已有账号（直接加入）。 */
export function AddTenantMemberModal({ slug, onClose }: { slug: string; onClose: () => void }) {
  const add = useAddTenantMember(slug);
  const [form, setForm] = useState<AddForm>(EMPTY);
  const patch = (next: Partial<AddForm>) => {
    setForm((current) => ({ ...current, ...next }));
    if (add.error) add.reset();
  };
  const hasPassword = Boolean(form.password || form.confirm);
  const canSubmit =
    isUsernameValid(form.username.trim()) && (!hasPassword || isNewPasswordValid(form.password, form.confirm));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || add.isPending) return;
    add.mutate(toPayload(form), {
      onSuccess: (member) => {
        notifications.show({ color: 'ink', message: `已把「${member.display_name}」加入账套` });
        onClose();
      },
    });
  };

  return (
    <Modal opened onClose={onClose} title={`添加成员：${slug}`}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <Text size="xs" c="dimmed">{INTRO}</Text>
          <TextInput
            label="用户名"
            autoComplete="off"
            data-autofocus
            value={form.username}
            error={usernameError(form.username.trim())}
            onChange={(event) => patch({ username: event.currentTarget.value })}
          />
          <TextInput label="姓名" value={form.displayName} onChange={(event) => patch({ displayName: event.currentTarget.value })} />
          <RoleControl value={form.role} onChange={(role) => patch({ role })} />
          <NewPasswordFields
            password={form.password}
            confirm={form.confirm}
            onPasswordChange={(password) => patch({ password })}
            onConfirmChange={(confirm) => patch({ confirm })}
            passwordLabel="初始密码（新账号必填）"
          />
          <FormError error={add.error} />
          <ModalActions submitLabel="添加成员" isSubmitting={add.isPending} canSubmit={canSubmit} onCancel={onClose} />
        </Stack>
      </form>
    </Modal>
  );
}
