import { Anchor, Button, Stack, Text, TextInput } from '@mantine/core';
import { useState, type FormEvent } from 'react';
import { errorMessage } from '../../api/client';
import { useJoinTenant } from '../../api/hooks/auth';
import type { JoinInput } from '../../api/types';
import { AuthLayout } from '../../components/auth/AuthLayout';
import { NewPasswordFields } from '../../components/auth/NewPasswordFields';
import { isNewPasswordValid } from '../../lib/password';
import { saveRememberedUsername } from '../../lib/rememberedUsername';
import { DISPLAY_NAME_MAX_LENGTH, displayNameError, isUsernameValid, usernameError } from '../../lib/users';

interface JoinForm {
  code: string;
  username: string;
  displayName: string;
  password: string;
  confirm: string;
}

const EMPTY_FORM: JoinForm = { code: '', username: '', displayName: '', password: '', confirm: '' };

const INTRO = '填写管理员给你的邀请码。已有账号请填写它的用户名与登录密码，新用户则就此开通。';

function toPayload(form: JoinForm): JoinInput {
  const displayName = form.displayName.trim();
  return {
    code: form.code.trim(),
    username: form.username.trim(),
    password: form.password,
    ...(displayName ? { display_name: displayName } : {}),
  };
}

function isFormValid(form: JoinForm): boolean {
  const isNameOk = isUsernameValid(form.username.trim()) && !displayNameError(form.displayName);
  return Boolean(form.code.trim()) && isNameOk && isNewPasswordValid(form.password, form.confirm);
}

/** 邀请码加入页：成功后刷新认证状态，AuthGate 直接渲染应用。 */
export function JoinPage({ onBack }: { onBack: () => void }) {
  const join = useJoinTenant();
  const [form, setForm] = useState<JoinForm>(EMPTY_FORM);
  const patch = (next: Partial<JoinForm>) => {
    setForm((current) => ({ ...current, ...next }));
    if (join.error) join.reset();
  };
  const canSubmit = isFormValid(form);
  const error = join.error ? errorMessage(join.error) : null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || join.isPending) return;
    const payload = toPayload(form);
    join.mutate(payload, { onSuccess: () => saveRememberedUsername(payload.username) });
  };

  const footer = (
    <Anchor component="button" type="button" size="xs" onClick={onBack}>
      已有账号，直接登录
    </Anchor>
  );

  return (
    <AuthLayout title="加入账套" subtitle={INTRO} footer={footer}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <TextInput label="邀请码" autoComplete="off" spellCheck={false} autoFocus
            value={form.code} onChange={(event) => patch({ code: event.currentTarget.value })} />
          <TextInput label="用户名" autoComplete="username" autoCapitalize="none" spellCheck={false}
            value={form.username} error={usernameError(form.username.trim())}
            onChange={(event) => patch({ username: event.currentTarget.value })} />
          <TextInput label="姓名" description="显示为上传人、操作人；留空则同用户名"
            maxLength={DISPLAY_NAME_MAX_LENGTH} value={form.displayName} error={displayNameError(form.displayName)}
            onChange={(event) => patch({ displayName: event.currentTarget.value })} />
          <NewPasswordFields
            password={form.password}
            confirm={form.confirm}
            onPasswordChange={(password) => patch({ password })}
            onConfirmChange={(confirm) => patch({ confirm })}
            passwordLabel="密码"
          />
          {error && <Text size="sm" c="red.7" role="alert">{error}</Text>}
        </Stack>
        <Button type="submit" variant="filled" fullWidth size="md" mt="xl" loading={join.isPending} disabled={!canSubmit}>
          加入并进入
        </Button>
      </form>
    </AuthLayout>
  );
}
