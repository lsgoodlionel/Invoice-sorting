import { Button, PasswordInput } from '@mantine/core';
import { useState, type FormEvent } from 'react';
import { errorMessage } from '../../api/client';
import { useLogin } from '../../api/hooks/auth';
import { AuthLayout, BRAND_NAME } from '../../components/auth/AuthLayout';
import { ResetPasswordHint } from '../../components/auth/ResetPasswordHint';

/** 登录页：成功后刷新认证状态，AuthGate 在当前 URL 上直接渲染应用。 */
export function LoginPage() {
  const login = useLogin();
  const [password, setPassword] = useState('');
  const error = login.error ? errorMessage(login.error) : null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!password || login.isPending) return;
    login.mutate(password);
  };

  const change = (value: string) => {
    setPassword(value);
    if (login.error) login.reset();
  };

  return (
    <AuthLayout title={BRAND_NAME} subtitle="请输入登录密码以继续。">
      <form onSubmit={submit} noValidate>
        <PasswordInput
          label="密码"
          name="password"
          autoComplete="current-password"
          autoFocus
          value={password}
          error={error}
          aria-invalid={Boolean(error)}
          onChange={(event) => change(event.currentTarget.value)}
        />
        <Button type="submit" variant="filled" fullWidth mt="md" loading={login.isPending} disabled={!password}>
          登录
        </Button>
      </form>
      <ResetPasswordHint />
    </AuthLayout>
  );
}
