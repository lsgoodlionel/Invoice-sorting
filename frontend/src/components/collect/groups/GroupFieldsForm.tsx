import { SimpleGrid, Switch, TextInput } from '@mantine/core';
import { DateInput } from '@mantine/dates';
import type { GroupDraft, GroupFields } from '../../../lib/importGroups';
import { CategorySelect } from '../../CategorySelect';
import { CurrencyAmountInputs } from '../../CurrencyAmountInputs';
import { MoneyInput } from '../../MoneyInput';
import { ProjectSelect } from '../../ProjectSelect';

interface GroupFieldsFormProps {
  group: GroupDraft;
  onChange: (patch: Partial<GroupFields>) => void;
}

/** 组摘要：新建记录时使用的字段；非“新建”操作时只读。 */
export function GroupFieldsForm({ group, onChange }: GroupFieldsFormProps) {
  const isDisabled = group.operation.type !== 'create';
  const isCreate = !isDisabled;
  return (
    <SimpleGrid cols={{ base: 2, lg: 4 }} spacing="xs" verticalSpacing={6}>
      <DateInput
        size="xs"
        label="日期"
        aria-label="日期"
        valueFormat="YYYY-MM-DD"
        value={group.spentOn}
        disabled={isDisabled}
        error={isCreate && !group.spentOn}
        onChange={(spentOn) => onChange({ spentOn })}
      />
      <TextInput
        size="xs"
        label="商家"
        aria-label="商家"
        placeholder="未识别，请填写"
        value={group.merchant}
        disabled={isDisabled}
        onChange={(event) => onChange({ merchant: event.currentTarget.value })}
      />
      <TextInput
        size="xs"
        label="摘要"
        aria-label="摘要"
        value={group.summary}
        disabled={isDisabled}
        onChange={(event) => onChange({ summary: event.currentTarget.value })}
      />
      <MoneyInput
        size="xs"
        label="人民币金额"
        aria-label="人民币金额"
        placeholder="请填写"
        cents={group.amountCents}
        disabled={isDisabled}
        error={isCreate && group.amountCents === null}
        onCentsChange={(amountCents) => onChange({ amountCents })}
      />
      <CurrencyAmountInputs
        size="xs"
        currency={group.currency}
        originalCents={group.originalAmountCents}
        disabled={isDisabled}
        onCurrencyChange={(currency) => onChange({ currency })}
        onOriginalChange={(originalAmountCents) => onChange({ originalAmountCents })}
      />
      <CategorySelect size="xs" label="分类" aria-label="分类" clearable value={group.categoryId} disabled={isDisabled} onChange={(categoryId) => onChange({ categoryId })} />
      <ProjectSelect size="xs" label="经费项目" aria-label="经费项目" clearable creatable={false} value={group.projectId} disabled={isDisabled} onChange={(projectId) => onChange({ projectId })} />
      <Switch size="xs" mt={22} label="网购" aria-label="网购" checked={group.isOnline} disabled={isDisabled} onChange={(event) => onChange({ isOnline: event.currentTarget.checked })} />
      <Switch size="xs" mt={22} label="免发票（境外）" aria-label="免发票（境外）" checked={group.invoiceExempt} disabled={isDisabled} onChange={(event) => onChange({ invoiceExempt: event.currentTarget.checked })} />
    </SimpleGrid>
  );
}
