import { Button, Group, NumberInput, Select, SimpleGrid, Stack, TextInput } from '@mantine/core';
import type { MailTls } from '../../../api/mailTypes';
import {
  MAIL_PRESETS,
  PORT_MAX,
  PORT_MIN,
  TLS_OPTIONS,
  applyPreset,
  portForTls,
  type MailDraft,
} from '../../../lib/mail';
import { MailPasswordField } from './MailPasswordField';

interface MailSettingsFormProps {
  draft: MailDraft;
  isReadOnly: boolean;
  passwordSet: boolean;
  passwordError: string;
  onChange: (next: MailDraft) => void;
}

const PRESET_OPTIONS = MAIL_PRESETS.map((preset) => ({ value: preset.value, label: preset.label }));
const NOTIFY_DESCRIPTION = '有新申请待审批时给这些地址发提醒；多个用英文逗号分隔，最多 5 个，留空则不发';

/** 邮件服务器参数表单（受控）：预设、服务器、加密方式与端口、账号密码、发件人、站点地址。 */
export function MailSettingsForm({ draft, isReadOnly, passwordSet, passwordError, onChange }: MailSettingsFormProps) {
  const patch = (next: Partial<MailDraft>) => onChange({ ...draft, ...next });
  const pickPreset = (value: string | null) => {
    const preset = MAIL_PRESETS.find((item) => item.value === value);
    if (preset) onChange(applyPreset(draft, preset));
  };
  const changeTls = (value: string | null) => {
    if (!value) return;
    const tls = value as MailTls;
    patch({ tls, port: portForTls(tls, draft.port) });
  };
  const common = { readOnly: isReadOnly, disabled: isReadOnly };

  return (
    <Stack gap="sm">
      {!isReadOnly && (
        <Select label="常用邮箱" placeholder="选择后自动填入服务器、端口与加密方式" data={PRESET_OPTIONS}
          value={null} onChange={pickPreset} clearable={false} allowDeselect={false} />
      )}
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
        <TextInput label="SMTP 服务器" placeholder="smtp.example.com" value={draft.host} {...common}
          onChange={(event) => patch({ host: event.currentTarget.value })} />
        <Select label="加密方式" data={TLS_OPTIONS} value={draft.tls} allowDeselect={false} {...common}
          onChange={changeTls} />
        <NumberInput label="端口" min={PORT_MIN} max={PORT_MAX} allowDecimal={false} value={draft.port} {...common}
          onChange={(value) => patch({ port: Number(value) || 0 })} />
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
        <TextInput label="账号" placeholder="通常是完整邮箱地址" autoComplete="off" value={draft.username} {...common}
          onChange={(event) => patch({ username: event.currentTarget.value })} />
        <MailPasswordField isSet={passwordSet} error={passwordError} action={draft.passwordAction} value={draft.password}
          isReadOnly={isReadOnly}
          onChange={(password) => patch({ password, passwordAction: password ? 'set' : 'keep' })}
          onClear={() => patch({ password: '', passwordAction: 'clear' })}
          onUndo={() => patch({ password: '', passwordAction: 'keep' })} />
      </SimpleGrid>
      <TextInput label="发件人" description="邮箱地址，或「名称 <邮箱地址>」；多数邮箱要求与账号一致"
        placeholder="发票报销 <noreply@example.com>" value={draft.sender} {...common}
        onChange={(event) => patch({ sender: event.currentTarget.value })} />
      <Group align="flex-end" gap="xs" wrap="nowrap">
        <TextInput style={{ flex: 1 }} label="站点地址" description="邮件里的注册链接与推荐链接用这个地址开头"
          placeholder="https://fp.example.com" value={draft.public_base_url} {...common}
          onChange={(event) => patch({ public_base_url: event.currentTarget.value })} />
        {!isReadOnly && (
          <Button variant="default" onClick={() => patch({ public_base_url: window.location.origin })}>使用当前地址</Button>
        )}
      </Group>
      <TextInput label="通知接收邮箱" description={NOTIFY_DESCRIPTION} placeholder="ops@example.com,boss@example.com"
        autoComplete="off" value={draft.notify_emails} {...common}
        onChange={(event) => patch({ notify_emails: event.currentTarget.value })} />
    </Stack>
  );
}
