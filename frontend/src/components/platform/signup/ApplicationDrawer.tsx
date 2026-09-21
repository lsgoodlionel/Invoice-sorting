import { Alert, Button, Drawer, Group, Stack } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { useResendApplicationEmail } from '../../../api/hooks/platformSignup';
import type { MailDelivery, PlatformApplication, ReviewResult } from '../../../api/signupTypes';
import { isUndelivered } from '../../../lib/signup';
import { FormError } from '../../settings/users/FormError';
import { ApplicationDetails } from './ApplicationDetails';
import { ApproveModal } from './ApproveModal';
import { ManualNotice } from './ManualNotice';
import { RejectModal } from './RejectModal';

type Dialog = 'approve' | 'reject' | null;

const RESENDABLE = new Set(['approved', 'rejected']);
const PAST_UNDELIVERED = '上次通知没有送达申请人。点「重新发信」会换发新的注册链接（旧链接失效）并显示可转告的内容。';

/** 申请详情抽屉：全部资料、推荐人，批准 / 否决 / 重新发信。 */
export function ApplicationDrawer({ application, onClose }: { application: PlatformApplication; onClose: () => void }) {
  const [current, setCurrent] = useState(application);
  // 注册链接与通知文字只在本次审批/重发的响应里给出，关掉抽屉即不再可得
  const [notice, setNotice] = useState<MailDelivery | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const resend = useResendApplicationEmail();
  const isPending = current.status === 'pending';
  const canResend = RESENDABLE.has(current.status) && !current.is_purged;

  const settle = (result: ReviewResult, action: string) => {
    setCurrent(result.application);
    setNotice(result.notice);
    setDialog(null);
    if (result.notice.mail_status === 'sent') notifications.show({ color: 'ink', message: `${action}，已发邮件通知申请人` });
  };

  const showManual = notice !== null && isUndelivered(notice.mail_status);
  return (
    <Drawer opened onClose={onClose} position="right" size="lg" title={`注册申请：${current.name}`}>
      <Stack gap="lg">
        <ApplicationDetails application={current} />
        {showManual && <ManualNotice delivery={notice} email={current.email} />}
        {!notice && canResend && isUndelivered(current.mail_status) && (
          <Alert color="orange" variant="light">{PAST_UNDELIVERED}</Alert>
        )}
        <FormError error={resend.error} />
        <Group>
          {isPending && <Button variant="filled" onClick={() => setDialog('approve')}>批准</Button>}
          {isPending && <Button variant="outline" color="red" onClick={() => setDialog('reject')}>否决</Button>}
          {canResend && (
            <Button variant="outline" loading={resend.isPending}
              onClick={() => resend.mutate(current.id, { onSuccess: (result) => settle(result, '已重新发送') })}>
              重新发信
            </Button>
          )}
        </Group>
      </Stack>
      {dialog === 'approve' && (
        <ApproveModal application={current} onClose={() => setDialog(null)} onDone={(result) => settle(result, '已批准')} />
      )}
      {dialog === 'reject' && (
        <RejectModal application={current} onClose={() => setDialog(null)} onDone={(result) => settle(result, '已否决')} />
      )}
    </Drawer>
  );
}
