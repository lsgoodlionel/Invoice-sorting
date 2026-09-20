import { Anchor, Button, PasswordInput, Stack, Text, TextInput } from '@mantine/core';
import { useState, type ChangeEvent, type FormEvent } from 'react';
import { errorMessage } from '../../api/client';
import { useAuthStatus, useLogin } from '../../api/hooks/auth';
import { AuthLayout } from '../../components/auth/AuthLayout';
import { loadRememberedUsername, saveRememberedUsername } from '../../lib/rememberedUsername';
import { JoinPage } from './JoinPage';

const RESET_HINT = '忘记密码？请联系管理员重置';

/** 页脚：多租户部署额外给出邀请码入口；单租户部署只保留原来的一行提示。 */
function LoginFooter({ isMultiTenant, onJoin }: { isMultiTenant: boolean; onJoin: () => void }) {
  if (!isMultiTenant) return RESET_HINT;
  return (
    <Stack gap={4}>
      <Text size="xs" c="dimmed">{RESET_HINT}</Text>
      <Anchor component="button" type="button" size="xs" onClick={onJoin}>有邀请码？加入账套</Anchor>
    </Stack>
  );
}

/** 登录表单状态：用户名默认上次成功登录的用户名（首次为 admin），修改输入时清除错误。 */
function useLoginForm() {
  const login = useLogin();
  const [username, setUsername] = useState(loadRememberedUsername);
  const [password, setPassword] = useState('');
  const trimmedUsername = username.trim();
  const canSubmit = Boolean(trimmedUsername) && Boolean(password);

  const bind = (setter: (value: string) => void) => (event: ChangeEvent<HTMLInputElement>) => {
    setter(event.currentTarget.value);
    if (login.error) login.reset();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || login.isPending) return;
    login.mutate({ username: trimmedUsername, password }, { onSuccess: () => saveRememberedUsername(trimmedUsername) });
  };

  return { login, username, password, canSubmit, submit, onUsername: bind(setUsername), onPassword: bind(setPassword) };
}

/** 登录页：成功后刷新认证状态，AuthGate 在当前 URL 上直接渲染应用。 */
export function LoginPage() {
  const { login, username, password, canSubmit, submit, onUsername, onPassword } = useLoginForm();
  const { data: status } = useAuthStatus();
  const [isJoining, setJoining] = useState(false);
  const error = login.error ? errorMessage(login.error) : null;

  if (isJoining) return <JoinPage onBack={() => setJoining(false)} />;

  return (
    <AuthLayout
      title="登录"
      footer={<LoginFooter isMultiTenant={Boolean(status?.multi_tenant)} onJoin={() => setJoining(true)} />}
    >
      <form onSubmit={submit} noValidate>
        <Stack gap="md">
          <TextInput label="用户名" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false}
            autoFocus={!username} value={username} aria-invalid={Boolean(error)} onChange={onUsername} />
          <PasswordInput label="密码" name="password" autoComplete="current-password"
            autoFocus={Boolean(username)} value={password} aria-invalid={Boolean(error)} onChange={onPassword} />
          {error && <Text size="sm" c="red.7" role="alert">{error}</Text>}
        </Stack>
        <Button type="submit" variant="filled" fullWidth size="md" mt="xl" loading={login.isPending} disabled={!canSubmit}>
          登录
        </Button>
      </form>
    </AuthLayout>
  );
}
