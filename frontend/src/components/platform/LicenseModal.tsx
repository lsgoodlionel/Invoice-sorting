import { Modal, NumberInput, Stack, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type FormEvent } from 'react';
import { useIssueLicense, useUpdateLicense } from '../../api/hooks/platform';
import type { LicenseRecord } from '../../api/types';
import { FormError } from '../settings/users/FormError';
import { ModalActions } from '../settings/users/ModalActions';

const USERS_MAX = 1_000_000;

interface LicenseForm {
  customerName: string;
  maxUsers: number;
  validUntil: string;
  note: string;
}

function initial(record?: LicenseRecord): LicenseForm {
  return {
    customerName: record?.customer_name ?? '',
    maxUsers: record?.max_users ?? 0,
    validUntil: record?.valid_until ?? '',
    note: record?.note ?? '',
  };
}

interface Props {
  record?: LicenseRecord;
  onIssued?: (record: LicenseRecord) => void;
  onClose: () => void;
}

/** 签发或修改授权记录；密钥由服务端生成，这里只填客户信息与有效期。 */
export function LicenseModal({ record, onIssued, onClose }: Props) {
  const issue = useIssueLicense();
  const update = useUpdateLicense();
  const action = record ? update : issue;
  const [form, setForm] = useState<LicenseForm>(initial(record));
  const patch = (next: Partial<LicenseForm>) => {
    setForm((current) => ({ ...current, ...next }));
    if (action.error) action.reset();
  };
  const canSubmit = form.customerName.trim().length > 0;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || action.isPending) return;
    const payload = {
      customer_name: form.customerName.trim(),
      max_users: form.maxUsers,
      valid_until: form.validUntil || null,
      note: form.note.trim(),
    };
    if (record) {
      update.mutate({ id: record.id, patch: payload }, { onSuccess: () => finish('已保存授权记录') });
      return;
    }
    issue.mutate(payload, {
      onSuccess: (created) => {
        onIssued?.(created);
        finish(`已为「${created.customer_name}」签发授权`);
      },
    });
  };

  const finish = (message: string) => {
    notifications.show({ color: 'ink', message });
    onClose();
  };

  return (
    <Modal opened onClose={onClose} title={record ? `编辑授权：${record.customer_name}` : '签发授权'}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <TextInput
            label="客户名称"
            data-autofocus
            value={form.customerName}
            onChange={(event) => patch({ customerName: event.currentTarget.value })}
          />
          <NumberInput
            label="用户数上限"
            description="0 表示不限制"
            min={0}
            max={USERS_MAX}
            value={form.maxUsers}
            onChange={(value) => patch({ maxUsers: Number(value) || 0 })}
          />
          <TextInput
            label="有效期至"
            type="date"
            description="留空表示永久授权"
            value={form.validUntil}
            onChange={(event) => patch({ validUntil: event.currentTarget.value })}
          />
          <TextInput label="备注" value={form.note} onChange={(event) => patch({ note: event.currentTarget.value })} />
          <FormError error={action.error} />
          <ModalActions submitLabel={record ? '保存' : '签发授权'} isSubmitting={action.isPending} canSubmit={canSubmit} onCancel={onClose} />
        </Stack>
      </form>
    </Modal>
  );
}
