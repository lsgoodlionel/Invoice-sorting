import { Stack, TextInput, Textarea } from '@mantine/core';
import {
  APPLY_IDENTITY_MAX,
  APPLY_LEDGER_NAME_MAX,
  APPLY_NAME_MAX,
  APPLY_NEEDS_MAX,
  applyFormErrors,
  type ApplyForm,
} from '../../lib/signup';

interface ApplyFormFieldsProps {
  form: ApplyForm;
  onChange: (next: Partial<ApplyForm>) => void;
}

/** 诱饵字段：移出可视区域、不可聚焦、读屏器忽略；只有机器人会填。 */
function HoneypotField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="signup-hp" aria-hidden="true">
      <label>
        网址
        <input name="website" type="text" tabIndex={-1} autoComplete="off" value={value}
          onChange={(event) => onChange(event.currentTarget.value)} />
      </label>
    </div>
  );
}

/** 申请表字段：姓名、邮箱、单位或身份、需求简介必填，期望账本名称选填。 */
export function ApplyFormFields({ form, onChange }: ApplyFormFieldsProps) {
  const errors = applyFormErrors(form);
  return (
    <Stack gap="sm">
      <TextInput label="姓名" autoComplete="name" autoFocus maxLength={APPLY_NAME_MAX}
        value={form.name} onChange={(event) => onChange({ name: event.currentTarget.value })} />
      <TextInput label="邮箱" type="email" autoComplete="email" spellCheck={false}
        description="审批结果与注册链接会发到这个邮箱"
        value={form.email} error={errors.email}
        onChange={(event) => onChange({ email: event.currentTarget.value })} />
      <TextInput label="单位或身份" placeholder="例如：某某大学经济学院 / 自由职业" maxLength={APPLY_IDENTITY_MAX}
        value={form.identity} onChange={(event) => onChange({ identity: event.currentTarget.value })} />
      <Textarea label="使用需求简介" placeholder="打算用它管理哪些报销？大概多少人使用？"
        autosize minRows={3} maxRows={8} maxLength={APPLY_NEEDS_MAX}
        value={form.needs} onChange={(event) => onChange({ needs: event.currentTarget.value })} />
      <TextInput label="期望账本名称" description="选填，批准时平台可调整" maxLength={APPLY_LEDGER_NAME_MAX}
        value={form.ledgerName} onChange={(event) => onChange({ ledgerName: event.currentTarget.value })} />
      <HoneypotField value={form.website} onChange={(website) => onChange({ website })} />
    </Stack>
  );
}
