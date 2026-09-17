import { Modal, Stack, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type FormEvent } from 'react';
import { useCreateUser } from '../../../api/hooks/users';
import type { UserCreate, UserRole } from '../../../api/types';
import { isNewPasswordValid } from '../../../lib/password';
import { DISPLAY_NAME_MAX_LENGTH, USERNAME_MAX_LENGTH, USERNAME_MIN_LENGTH, displayNameError, isUsernameValid, usernameError } from '../../../lib/users';
import { NewPasswordFields } from '../../auth/NewPasswordFields';
import { FormError } from './FormError';
import { ModalActions } from './ModalActions';
import { RoleControl } from './RoleControl';

interface CreateForm {
  username: string;
  displayName: string;
  role: UserRole;
  password: string;
  confirm: string;
}

type PatchForm = (next: Partial<CreateForm>) => void;

const EMPTY_FORM: CreateForm = { username: '', displayName: '', role: 'member', password: '', confirm: '' };

function toPayload(form: CreateForm): UserCreate {
  const displayName = form.displayName.trim();
  return {
    username: form.username.trim(),
    ...(displayName ? { display_name: displayName } : {}),
    password: form.password,
    role: form.role,
  };
}

function isFormValid(form: CreateForm): boolean {
  return isUsernameValid(form.username.trim()) && !displayNameError(form.displayName) && isNewPasswordValid(form.password, form.confirm);
}

function IdentityFields({ form, patch }: { form: CreateForm; patch: PatchForm }) {
  return (
    <>
      <TextInput
        label="用户名"
        description={`${USERNAME_MIN_LENGTH}–${USERNAME_MAX_LENGTH} 个字符，字母、数字、下划线、点、连字符；用于登录`}
        autoComplete="off"
        autoCapitalize="none"
        spellCheck={false}
        data-autofocus
        value={form.username}
        error={usernameError(form.username.trim())}
        onChange={(event) => patch({ username: event.currentTarget.value })}
      />
      <TextInput
        label="姓名"
        description="显示为上传人、操作人；留空则同用户名"
        maxLength={DISPLAY_NAME_MAX_LENGTH}
        value={form.displayName}
        error={displayNameError(form.displayName)}
        onChange={(event) => patch({ displayName: event.currentTarget.value })}
      />
    </>
  );
}

export function CreateUserModal({ onClose }: { onClose: () => void }) {
  const create = useCreateUser();
  const [form, setForm] = useState<CreateForm>(EMPTY_FORM);
  const patch: PatchForm = (next) => {
    setForm((current) => ({ ...current, ...next }));
    if (create.error) create.reset();
  };
  const canSubmit = isFormValid(form);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || create.isPending) return;
    create.mutate(toPayload(form), {
      onSuccess: (created) => {
        notifications.show({ color: 'ink', message: `已添加用户「${created.display_name}」` });
        onClose();
      },
    });
  };

  return (
    <Modal opened onClose={onClose} title="添加用户">
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <IdentityFields form={form} patch={patch} />
          <RoleControl value={form.role} onChange={(role) => patch({ role })} />
          <NewPasswordFields
            password={form.password}
            confirm={form.confirm}
            onPasswordChange={(password) => patch({ password })}
            onConfirmChange={(confirm) => patch({ confirm })}
            passwordLabel="初始密码"
          />
          <FormError error={create.error} />
          <ModalActions submitLabel="创建用户" isSubmitting={create.isPending} canSubmit={canSubmit} onCancel={onClose} />
        </Stack>
      </form>
    </Modal>
  );
}
