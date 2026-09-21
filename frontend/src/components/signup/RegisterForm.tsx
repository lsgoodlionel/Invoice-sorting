import { Button, Stack, Text, TextInput } from '@mantine/core';
import { useState, type FormEvent } from 'react';
import { errorMessage } from '../../api/client';
import { useRegister } from '../../api/hooks/signup';
import type { RegisterCodeInfo } from '../../api/signupTypes';
import { isNewPasswordValid } from '../../lib/password';
import { saveRememberedUsername } from '../../lib/rememberedUsername';
import { formatDateTime } from '../../lib/signup';
import { isUsernameValid, usernameError } from '../../lib/users';
import { AuthLayout } from '../auth/AuthLayout';
import { NewPasswordFields } from '../auth/NewPasswordFields';

interface RegisterFormProps {
  code: string;
  info: RegisterCodeInfo;
}

/** 注册表单：邮箱只读（绑定注册码），设置用户名与密码后开通账套并直接登录。 */
export function RegisterForm({ code, info }: RegisterFormProps) {
  const register = useRegister();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const trimmed = username.trim();
  const canSubmit = isUsernameValid(trimmed) && isNewPasswordValid(password, confirm);

  const edit = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    if (register.error) register.reset();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || register.isPending) return;
    register.mutate({ code, email: info.email, username: trimmed, password }, { onSuccess: () => saveRememberedUsername(trimmed) });
  };

  const ledger = info.ledger_name ? `「${info.ledger_name}」` : '一个独立账本';
  const expiry = info.expires_at ? `链接有效期至 ${formatDateTime(info.expires_at)}。` : '';
  const subtitle = `注册后会为你开通${ledger}，你是它的管理员。${expiry}`;
  return (
    <AuthLayout title="完成注册" subtitle={subtitle}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <TextInput label="邮箱" value={info.email} readOnly variant="filled" description="与申请时填写的邮箱一致，不能修改" />
          <TextInput label="用户名" autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus
            value={username} error={usernameError(trimmed)}
            onChange={(event) => edit(setUsername)(event.currentTarget.value)} />
          <NewPasswordFields password={password} confirm={confirm} passwordLabel="密码"
            onPasswordChange={edit(setPassword)} onConfirmChange={edit(setConfirm)} />
          {register.error && <Text size="sm" c="red.7" role="alert">{errorMessage(register.error)}</Text>}
        </Stack>
        <Button type="submit" variant="filled" fullWidth size="md" mt="xl" loading={register.isPending} disabled={!canSubmit}>
          注册并进入
        </Button>
      </form>
    </AuthLayout>
  );
}
