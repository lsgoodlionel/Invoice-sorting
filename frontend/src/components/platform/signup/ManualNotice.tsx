import { Alert, Button, CopyButton, Group, Stack, Text, Textarea } from '@mantine/core';
import type { MailDelivery } from '../../../api/signupTypes';
import { manualNotice } from '../../../lib/signup';

function CopyAction({ value, label }: { value: string; label: string }) {
  return (
    <CopyButton value={value}>
      {({ copied, copy }) => (
        <Button size="compact-xs" variant="outline" onClick={copy}>{copied ? '已复制' : label}</Button>
      )}
    </CopyButton>
  );
}

interface ManualNoticeProps {
  delivery: MailDelivery;
  email: string;
}

/** 邮件未配置或发送失败：给出注册链接与可复制的通知文字，由管理员手动转告。 */
export function ManualNotice({ delivery, email }: ManualNoticeProps) {
  const title = delivery.mail_status === 'failed' ? '通知邮件发送失败' : '未配置邮件服务，没有发出通知';
  const { link, text } = manualNotice(delivery, window.location.origin);
  return (
    <Alert color="orange" variant="light" title={title} data-testid="manual-notice">
      <Stack gap="xs">
        <Text size="sm" fw={600}>请手动转告申请人（{email}）。</Text>
        {delivery.mail_error && <Text size="xs" c="red.7">{delivery.mail_error}</Text>}
        {link && (
          <Group gap="xs" wrap="nowrap">
            <Text size="xs" className="num" style={{ wordBreak: 'break-all' }} data-testid="register-url">{link}</Text>
            <CopyAction value={link} label="复制注册链接" />
          </Group>
        )}
        {text && (
          <>
            <Textarea label="通知文字" value={text} readOnly autosize minRows={3} maxRows={10} />
            <Group><CopyAction value={text} label="复制通知文字" /></Group>
          </>
        )}
        {link && <Text size="xs" c="dimmed">注册链接只在这里显示一次；关掉后如需再次转告，请点「重新发信」换发新链接。</Text>}
      </Stack>
    </Alert>
  );
}
