import { Button, Group, PasswordInput, Text } from '@mantine/core';
import type { PasswordAction } from '../../../lib/mail';

interface MailPasswordFieldProps {
  isSet: boolean;
  /** 已保存的密码无法解密时的提示（需重新填写） */
  error: string;
  action: PasswordAction;
  value: string;
  isReadOnly: boolean;
  onChange: (value: string) => void;
  onClear: () => void;
  onUndo: () => void;
}

const HINT = '大多数邮箱需使用「授权码」而非登录密码，可在邮箱网页版的设置里开启 SMTP 后生成。';

/** SMTP 密码：已设置时留空不修改，可清除；密码本身从不回显。 */
export function MailPasswordField({ isSet, error, action, value, isReadOnly, onChange, onClear, onUndo }: MailPasswordFieldProps) {
  if (action === 'clear') {
    return (
      <Group gap="xs">
        <Text size="sm" c="orange.8">保存后将清除已保存的密码。</Text>
        <Button variant="subtle" size="compact-sm" onClick={onUndo}>撤销</Button>
      </Group>
    );
  }
  const placeholder = isSet ? '已设置，留空不修改' : '未设置';
  const canClear = isSet && !isReadOnly && !value;
  return (
    <PasswordInput
      label="密码 / 授权码"
      description={HINT}
      placeholder={placeholder}
      autoComplete="new-password"
      value={value}
      readOnly={isReadOnly}
      disabled={isReadOnly}
      error={error || undefined}
      onChange={(event) => onChange(event.currentTarget.value)}
      rightSectionWidth={canClear ? 64 : undefined}
      rightSection={canClear ? <Button variant="subtle" size="compact-xs" onClick={onClear}>清除</Button> : undefined}
    />
  );
}
