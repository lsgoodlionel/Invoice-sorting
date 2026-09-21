import { Alert, Button, Divider, Group, Loader, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState, type ReactNode } from 'react';
import { useMailSettings, usePatchMailSettings } from '../../../api/hooks/platformMail';
import type { MailSettings } from '../../../api/mailTypes';
import { buildMailPatch, isDraftDirty, isPortValid, toMailDraft, type MailDraft } from '../../../lib/mail';
import { formatDateTime } from '../../../lib/signup';
import { FormError } from '../../settings/users/FormError';
import { MailCheckPanel } from './MailCheckPanel';
import { MailSettingsForm } from './MailSettingsForm';

const ENV_NOTICE = '邮件由服务器环境变量配置（INVOICE_SORTING_SMTP_*），网页上只读；如需修改请联系运维，或去掉环境变量改为网页配置。';
const NONE_NOTICE = '尚未配置邮件：审批结果不会自动发信，需要在申请详情里复制通知手动转告。';
const MSG_SAVE_FIRST = '有未保存的修改，保存后再测试（测试使用已保存的配置）。';
const MSG_NOT_CONFIGURED = '填写 SMTP 服务器与发件人并保存后即可测试。';

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Stack gap="xs">
      <Divider label={<span className="section-label">{label}</span>} labelPosition="left" />
      {children}
    </Stack>
  );
}

function blockedReason(settings: MailSettings, isDirty: boolean): string {
  if (isDirty) return MSG_SAVE_FIRST;
  return settings.is_configured ? '' : MSG_NOT_CONFIGURED;
}

function MailEditor({ settings }: { settings: MailSettings }) {
  const save = usePatchMailSettings();
  const [draft, setDraft] = useState<MailDraft>(() => toMailDraft(settings));
  const isEnv = settings.source === 'env';
  const isDirty = !isEnv && isDraftDirty(draft, settings);

  const submit = () =>
    save.mutate(buildMailPatch(draft), {
      onSuccess: (next) => {
        setDraft(toMailDraft(next));
        notifications.show({ color: 'ink', message: '邮件设置已保存' });
      },
    });

  return (
    <Stack gap="lg" maw={720}>
      {isEnv && <Alert color="ink" variant="light">{ENV_NOTICE}</Alert>}
      {settings.warning && <Alert color="orange" variant="light">{settings.warning}</Alert>}
      {settings.source === 'none' && <Alert color="orange" variant="light">{NONE_NOTICE}</Alert>}
      <Section label="发信服务器">
        <MailSettingsForm draft={draft} isReadOnly={isEnv} passwordSet={settings.password_set}
          passwordError={settings.password_error} onChange={setDraft} />
        {!isEnv && (
          <Group gap="sm">
            <Button variant="filled" loading={save.isPending} disabled={!isDirty || !isPortValid(draft.port)} onClick={submit}>
              保存
            </Button>
            {settings.updated_at && (
              <Text size="xs" c="dimmed">上次修改：{formatDateTime(settings.updated_at)} {settings.updated_by}</Text>
            )}
          </Group>
        )}
        <FormError error={save.error} />
      </Section>
      <Section label="验证">
        <MailCheckPanel lastCheck={settings.last_check} blockedReason={blockedReason(settings, isDirty)} />
      </Section>
    </Stack>
  );
}

/** 平台 → 邮件：平台管理员在网页上配置 SMTP 并直接验证；环境变量配置时只读。 */
export function MailSettingsManager() {
  const { data, isLoading } = useMailSettings();
  if (isLoading) return <Loader size="sm" />;
  if (!data) return null;
  return <MailEditor settings={data} />;
}
