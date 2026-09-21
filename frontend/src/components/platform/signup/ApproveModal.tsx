import { Modal, Select, Stack, Text, TextInput } from '@mantine/core';
import { useState, type FormEvent } from 'react';
import { usePlans } from '../../../api/hooks/platform';
import { useApproveApplication } from '../../../api/hooks/platformSignup';
import type { ApproveInput, PlatformApplication, ReviewResult } from '../../../api/signupTypes';
import { suggestSlug } from '../../../lib/signup';
import { FormError } from '../../settings/users/FormError';
import { ModalActions } from '../../settings/users/ModalActions';
import { SLUG_HINT, isSlugValid, slugError } from '../tenantForm';

interface ApproveForm {
  slug: string;
  name: string;
  planCode: string;
  expiresOn: string;
}

interface ApproveModalProps {
  application: PlatformApplication;
  onClose: () => void;
  onDone: (result: ReviewResult) => void;
}

function initialForm(application: PlatformApplication): ApproveForm {
  return {
    slug: '',
    name: application.ledger_name || `${application.name}的账本`,
    planCode: '',
    expiresOn: '',
  };
}

/** 留空的项不传，由后端按默认处理（标识自动生成、免费套餐、长期有效）。 */
function toPayload(form: ApproveForm): ApproveInput {
  const slug = form.slug.trim();
  const name = form.name.trim();
  return {
    ...(slug ? { slug } : {}),
    ...(name ? { name } : {}),
    ...(form.planCode ? { plan_code: form.planCode } : {}),
    ...(form.expiresOn ? { expires_on: form.expiresOn } : {}),
  };
}

/** 批准：可调整账套标识与名称、套餐与到期日；后端生成注册码并发信。 */
export function ApproveModal({ application, onClose, onDone }: ApproveModalProps) {
  const approve = useApproveApplication();
  const { data: plans = [] } = usePlans();
  const [form, setForm] = useState<ApproveForm>(() => initialForm(application));
  const patch = (next: Partial<ApproveForm>) => {
    setForm((current) => ({ ...current, ...next }));
    if (approve.error) approve.reset();
  };
  const slug = form.slug.trim();
  const canSubmit = !slug || isSlugValid(slug);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || approve.isPending) return;
    approve.mutate({ id: application.id, input: toPayload(form) }, { onSuccess: onDone });
  };

  return (
    <Modal opened onClose={onClose} title={`批准申请 ${application.number}`}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <Text size="xs" c="dimmed">批准后生成一次性注册码发往 {application.email}；对方注册时开通这个账套。</Text>
          <TextInput label="账套标识" description={`${SLUG_HINT}。留空自动生成`} data-autofocus
            placeholder={`${suggestSlug(application.email)}-xxxxxx`} value={form.slug} error={slugError(form.slug)}
            onChange={(event) => patch({ slug: event.currentTarget.value })} />
          <TextInput label="账套名称" value={form.name} onChange={(event) => patch({ name: event.currentTarget.value })} />
          <Select label="套餐" placeholder="不指定（按免费套餐）" clearable
            data={plans.map((plan) => ({ value: plan.code, label: plan.name || plan.code }))}
            value={form.planCode || null} onChange={(value) => patch({ planCode: value ?? '' })} />
          <TextInput label="到期日" type="date" description="留空表示长期有效" value={form.expiresOn}
            onChange={(event) => patch({ expiresOn: event.currentTarget.value })} />
          <FormError error={approve.error} />
          <ModalActions submitLabel="批准" isSubmitting={approve.isPending} canSubmit={canSubmit} onCancel={onClose} />
        </Stack>
      </form>
    </Modal>
  );
}
