import { Alert, Button, Group, Stack, Text, TextInput } from '@mantine/core';
import { useState } from 'react';
import { useSendTestMail, useTestMailConnection } from '../../../api/hooks/platformMail';
import type { MailCheckResult, MailLastCheck } from '../../../api/mailTypes';
import { checkCategoryLabel, checkKindLabel } from '../../../lib/mail';
import { formatDateTime } from '../../../lib/signup';
import { FormError } from '../../settings/users/FormError';

interface MailCheckPanelProps {
  lastCheck: MailLastCheck | null;
  /** 不能测试的原因（未配置、有未保存的修改）；空串表示可以测试 */
  blockedReason: string;
}

function LastCheck({ check }: { check: MailLastCheck }) {
  const status = check.ok ? '成功' : checkCategoryLabel(check.category);
  const who = check.checked_by ? ` · ${check.checked_by}` : '';
  return (
    <Alert color={check.ok ? 'teal' : 'red'} variant="light" data-testid="mail-last-check"
      role={check.ok ? undefined : 'alert'} title={`最近验证：${checkKindLabel(check.kind)} · ${status}`}>
      <Text size="sm">{check.message}</Text>
      <Text size="xs" c="dimmed">{formatDateTime(check.checked_at)}{who}</Text>
    </Alert>
  );
}

/** 测试连接（只登录不发信）与发送测试邮件；使用已保存并生效的配置。 */
export function MailCheckPanel({ lastCheck, blockedReason }: MailCheckPanelProps) {
  const connection = useTestMailConnection();
  const email = useSendTestMail();
  const [to, setTo] = useState('');
  // 本次测试的结果立即展示；重新读取设置后与「最近一次验证」一致
  const [latest, setLatest] = useState<MailLastCheck | null>(null);
  const isBusy = connection.isPending || email.isPending;
  const isBlocked = Boolean(blockedReason);

  const remember = (kind: MailLastCheck['kind']) => (result: MailCheckResult) =>
    setLatest({ ...result, kind, checked_by: '' });
  const runConnection = () => connection.mutate(undefined, { onSuccess: remember('connection') });
  const runEmail = () => email.mutate(to.trim(), { onSuccess: remember('email') });
  const shown = latest ?? lastCheck;

  return (
    <Stack gap="sm">
      {blockedReason && <Text size="sm" c="dimmed">{blockedReason}</Text>}
      <Group align="flex-end" gap="xs">
        <Button variant="light" loading={connection.isPending} disabled={isBlocked || isBusy} onClick={runConnection}>
          测试连接
        </Button>
        <TextInput w={260} label="测试收件地址" placeholder="you@example.com" type="email" value={to}
          onChange={(event) => setTo(event.currentTarget.value)} />
        <Button variant="light" loading={email.isPending} disabled={isBlocked || isBusy || !to.trim()} onClick={runEmail}>
          发送测试邮件
        </Button>
      </Group>
      <FormError error={connection.error ?? email.error} />
      {shown && <LastCheck check={shown} />}
    </Stack>
  );
}
