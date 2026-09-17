import { PasswordInput, Stack } from '@mantine/core';
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, confirmError, passwordError } from '../../lib/password';
import { PasswordStrengthHint } from './PasswordStrengthHint';

interface NewPasswordFieldsProps {
  password: string;
  confirm: string;
  onPasswordChange: (value: string) => void;
  onConfirmChange: (value: string) => void;
  passwordLabel?: string;
  confirmLabel?: string;
  autoFocus?: boolean;
}

/** 新密码 + 确认密码，带实时校验与强度提示。 */
export function NewPasswordFields({
  password,
  confirm,
  onPasswordChange,
  onConfirmChange,
  passwordLabel = '新密码',
  confirmLabel = '确认密码',
  autoFocus = false,
}: NewPasswordFieldsProps) {
  const lengthError = passwordError(password);
  const mismatchError = confirmError(password, confirm);
  return (
    <Stack gap="xs">
      <PasswordInput
        label={passwordLabel}
        description={`${PASSWORD_MIN_LENGTH}–${PASSWORD_MAX_LENGTH} 个字符`}
        name="new-password"
        autoComplete="new-password"
        autoFocus={autoFocus}
        value={password}
        error={lengthError}
        aria-invalid={Boolean(lengthError)}
        onChange={(event) => onPasswordChange(event.currentTarget.value)}
      />
      <PasswordStrengthHint password={password} />
      <PasswordInput
        label={confirmLabel}
        name="confirm-password"
        autoComplete="new-password"
        value={confirm}
        error={mismatchError}
        aria-invalid={Boolean(mismatchError)}
        onChange={(event) => onConfirmChange(event.currentTarget.value)}
      />
    </Stack>
  );
}
