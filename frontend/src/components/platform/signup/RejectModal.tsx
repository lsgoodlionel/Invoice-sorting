import { Modal, Stack, Text, Textarea } from '@mantine/core';
import { useState, type FormEvent } from 'react';
import { useRejectApplication } from '../../../api/hooks/platformSignup';
import type { PlatformApplication, ReviewResult } from '../../../api/signupTypes';
import { REJECT_REASON_MAX } from '../../../lib/signup';
import { FormError } from '../../settings/users/FormError';
import { ModalActions } from '../../settings/users/ModalActions';

interface RejectModalProps {
  application: PlatformApplication;
  onClose: () => void;
  onDone: (result: ReviewResult) => void;
}

/** 否决：原因可选，会写进通知邮件。 */
export function RejectModal({ application, onClose, onDone }: RejectModalProps) {
  const reject = useRejectApplication();
  const [reason, setReason] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (reject.isPending) return;
    reject.mutate({ id: application.id, input: { reason: reason.trim() } }, { onSuccess: onDone });
  };

  return (
    <Modal opened onClose={onClose} title={`否决申请 ${application.number}`}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <Text size="xs" c="dimmed">否决结果会通知 {application.email}；个人资料保留 180 天后自动删除。</Text>
          <Textarea label="原因（可选）" data-autofocus autosize minRows={3} maxLength={REJECT_REASON_MAX}
            value={reason} onChange={(event) => setReason(event.currentTarget.value)} />
          <FormError error={reject.error} />
          <ModalActions submitLabel="否决" isSubmitting={reject.isPending} canSubmit onCancel={onClose} />
        </Stack>
      </form>
    </Modal>
  );
}
