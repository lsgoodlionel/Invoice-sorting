import { Button, PasswordInput, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type FormEvent } from 'react';
import { ApiError, errorMessage } from '../../api/client';
import { useChangePassword } from '../../api/hooks/auth';
import { isNewPasswordValid } from '../../lib/password';
import { NewPasswordFields } from '../auth/NewPasswordFields';

const HTTP_BAD_REQUEST = 400;

interface PasswordForm {
  current: string;
  next: string;
  confirm: string;
}

const EMPTY_FORM: PasswordForm = { current: '', next: '', confirm: '' };

/** 当前密码错误（400）显示在“当前密码”下，其他错误显示在表单底部。 */
function splitError(error: unknown): { currentError: string | null; formError: string | null } {
  if (!error) return { currentError: null, formError: null };
  const message = errorMessage(error);
  const isCurrentWrong = error instanceof ApiError && error.status === HTTP_BAD_REQUEST;
  return isCurrentWrong ? { currentError: message, formError: null } : { currentError: null, formError: message };
}

export function ChangePasswordForm() {
  const change = useChangePassword();
  const [form, setForm] = useState<PasswordForm>(EMPTY_FORM);
  const patch = (next: Partial<PasswordForm>) => {
    setForm((current) => ({ ...current, ...next }));
    if (change.error) change.reset();
  };
  const canSubmit = Boolean(form.current) && isNewPasswordValid(form.next, form.confirm);
  const { currentError, formError } = splitError(change.error);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || change.isPending) return;
    change.mutate(
      { current_password: form.current, new_password: form.next },
      {
        onSuccess: () => {
          setForm(EMPTY_FORM);
          notifications.show({ color: 'ink', message: '密码已修改，其他设备需重新登录' });
        },
      },
    );
  };

  return (
    <form onSubmit={submit} noValidate style={{ maxWidth: 400 }}>
      <Stack gap="xs">
        <PasswordInput
          label="当前密码"
          name="current-password"
          autoComplete="current-password"
          value={form.current}
          error={currentError}
          aria-invalid={Boolean(currentError)}
          onChange={(event) => patch({ current: event.currentTarget.value })}
        />
        <NewPasswordFields
          password={form.next}
          confirm={form.confirm}
          onPasswordChange={(next) => patch({ next })}
          onConfirmChange={(confirm) => patch({ confirm })}
          confirmLabel="确认新密码"
        />
        {formError && (
          <Text size="sm" c="red.7" role="alert">
            {formError}
          </Text>
        )}
        <div>
          <Button type="submit" variant="filled" loading={change.isPending} disabled={!canSubmit}>
            修改密码
          </Button>
        </div>
      </Stack>
    </form>
  );
}
