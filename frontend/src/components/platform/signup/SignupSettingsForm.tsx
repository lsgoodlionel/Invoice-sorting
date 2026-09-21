import { Alert, Button, Group, NumberInput, SegmentedControl, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { usePatchSignupSettings, useSignupSettings } from '../../../api/hooks/platformSignup';
import type { SignupSettings, SignupSettingsPatch } from '../../../api/signupTypes';
import { CODE_VALID_DAYS_MAX, CODE_VALID_DAYS_MIN, REFERRAL_QUOTA_MAX } from '../../../lib/signup';
import { FormError } from '../../settings/users/FormError';

const MODE_OPTIONS = [
  { value: 'approval', label: '需审批' },
  { value: 'direct', label: '直接注册' },
];

type Draft = Required<SignupSettingsPatch>;

const toDraft = (settings: SignupSettings): Draft => ({
  require_approval: settings.require_approval,
  monthly_referral_quota: settings.monthly_referral_quota,
  code_valid_days: settings.code_valid_days,
});

const isSame = (first: Draft, second: Draft) =>
  (Object.keys(first) as (keyof Draft)[]).every((key) => first[key] === second[key]);

function SettingsEditor({ settings }: { settings: SignupSettings }) {
  const save = usePatchSignupSettings();
  const [draft, setDraft] = useState<Draft>(() => toDraft(settings));
  const patch = (next: Partial<Draft>) => setDraft((current) => ({ ...current, ...next }));
  const isDirty = !isSame(draft, toDraft(settings));
  const isValid = draft.code_valid_days >= CODE_VALID_DAYS_MIN && draft.code_valid_days <= CODE_VALID_DAYS_MAX && draft.monthly_referral_quota >= 0;

  const submit = () =>
    save.mutate(draft, { onSuccess: () => notifications.show({ color: 'ink', message: '注册设置已保存' }) });

  return (
    <Stack gap="sm" maw={420}>
      {!settings.is_mail_configured && (
        <Alert color="orange" variant="light">未配置邮件服务（SMTP）：审批结果不会自动发信，需要在申请详情里复制通知手动转告。</Alert>
      )}
      <Stack gap={4}>
        <Text size="sm" fw={500} id="signup-mode-label">推荐注册方式</Text>
        <SegmentedControl aria-labelledby="signup-mode-label" data={MODE_OPTIONS}
          value={draft.require_approval ? 'approval' : 'direct'}
          onChange={(value) => patch({ require_approval: value === 'approval' })} />
        <Text size="xs" c="dimmed">直接注册：被推荐人填完资料立即收到注册链接（仍需验证邮箱），超出每月名额自动转为需审批。</Text>
      </Stack>
      <NumberInput label="每月推荐名额" description="每位推荐人每月可直接注册的人数" min={0} max={REFERRAL_QUOTA_MAX}
        allowDecimal={false} value={draft.monthly_referral_quota}
        onChange={(value) => patch({ monthly_referral_quota: Number(value) || 0 })} />
      <NumberInput label="注册码有效天数" min={CODE_VALID_DAYS_MIN} max={CODE_VALID_DAYS_MAX} allowDecimal={false}
        value={draft.code_valid_days} onChange={(value) => patch({ code_valid_days: Number(value) || 0 })} />
      <FormError error={save.error} />
      <Group>
        <Button variant="filled" loading={save.isPending} disabled={!isDirty || !isValid} onClick={submit}>保存设置</Button>
      </Group>
    </Stack>
  );
}

/** 注册设置：审批开关、每月推荐名额、注册码有效天数。 */
export function SignupSettingsForm() {
  const { data } = useSignupSettings();
  if (!data) return null;
  return <SettingsEditor key={JSON.stringify(toDraft(data))} settings={data} />;
}
