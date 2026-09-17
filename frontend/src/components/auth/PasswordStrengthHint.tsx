import { Group, Progress, Text } from '@mantine/core';
import { passwordStrength, type StrengthLevel } from '../../lib/password';

const STRENGTH_COLORS: Readonly<Record<StrengthLevel, string>> = {
  none: 'paper.3',
  weak: 'red.6',
  medium: 'yellow.6',
  strong: 'ink.6',
};

/** 纯前端强度提示，不限制提交。 */
export function PasswordStrengthHint({ password }: { password: string }) {
  const strength = passwordStrength(password);
  if (strength.level === 'none') return null;
  return (
    <Group gap="xs" wrap="nowrap" aria-live="polite">
      <Progress value={strength.percent} color={STRENGTH_COLORS[strength.level]} size={4} style={{ flex: 1 }} aria-hidden="true" />
      <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
        强度：{strength.label}
        {strength.level !== 'strong' && '（建议 12 位以上，混合大小写、数字与符号）'}
      </Text>
    </Group>
  );
}
