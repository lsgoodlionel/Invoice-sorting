import { Alert, Anchor, Text } from '@mantine/core';
import { useMailStatus } from '../../../api/hooks/platformMail';

const MSG_NO_MAIL = '未配置邮件服务（SMTP）：审批结果不会自动发信，需要在申请详情里复制通知手动转告。';
const MSG_NO_NOTIFY = '未设置通知邮箱：有新申请待审批时不会发提醒邮件，请到「邮件」页签填写通知接收邮箱。';

interface HintProps {
  testId: string;
  message: string;
  action: string;
  onOpenMail?: () => void;
}

function Hint({ testId, message, action, onOpenMail }: HintProps) {
  return (
    <Alert color="orange" variant="light" py={8} data-testid={testId}>
      <Text size="sm" span>{message}</Text>
      {onOpenMail && (
        <Anchor component="button" type="button" size="sm" ml={4} onClick={onOpenMail}>{action}</Anchor>
      )}
    </Alert>
  );
}

/** 未配置邮件、或配了邮件但没填通知邮箱时的提示；给了 onOpenMail 时可一键跳到「邮件」页签。 */
export function MailNotConfiguredHint({ onOpenMail }: { onOpenMail?: () => void }) {
  const { isConfigured, hasNotifyEmails } = useMailStatus();
  if (isConfigured === false) {
    return <Hint testId="mail-not-configured" message={MSG_NO_MAIL} action="去配置邮件" onOpenMail={onOpenMail} />;
  }
  if (isConfigured && !hasNotifyEmails) {
    return <Hint testId="notify-emails-missing" message={MSG_NO_NOTIFY} action="去设置通知邮箱" onOpenMail={onOpenMail} />;
  }
  return null;
}
