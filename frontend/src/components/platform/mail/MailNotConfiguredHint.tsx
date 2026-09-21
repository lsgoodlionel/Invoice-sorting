import { Alert, Anchor, Text } from '@mantine/core';
import { useMailConfigured } from '../../../api/hooks/platformMail';

/** 未配置邮件时的提示；给了 onOpenMail 时可一键跳到「邮件」页签。 */
export function MailNotConfiguredHint({ onOpenMail }: { onOpenMail?: () => void }) {
  const isConfigured = useMailConfigured();
  if (isConfigured !== false) return null;
  return (
    <Alert color="orange" variant="light" py={8} data-testid="mail-not-configured">
      <Text size="sm" span>未配置邮件服务（SMTP）：审批结果不会自动发信，需要在申请详情里复制通知手动转告。</Text>
      {onOpenMail && (
        <Anchor component="button" type="button" size="sm" ml={4} onClick={onOpenMail}>去配置邮件</Anchor>
      )}
    </Alert>
  );
}
