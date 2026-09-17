import { Autocomplete, SimpleGrid, Switch, Textarea, TextInput } from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { useEffect, useState } from 'react';
import { useUpdateExpense } from '../../api/hooks/expenses';
import type { ExpenseDetail, ExpensePatch } from '../../api/types';
import { CategorySelect } from '../CategorySelect';
import { MoneyInput } from '../MoneyInput';
import { ProjectSelect } from '../ProjectSelect';

const PAY_METHODS = ['微信', '支付宝', '银行卡', '公务卡', '现金', '对公转账'];

type TextField = 'merchant' | 'summary' | 'pay_method' | 'note';

/** 可编辑字段：文本失焦保存，选择类即时保存；只提交变化的字段。 */
export function ExpenseFields({ expense }: { expense: ExpenseDetail }) {
  const update = useUpdateExpense(expense.id);
  const [texts, setTexts] = useState<Record<TextField, string>>(() => pickTexts(expense));

  useEffect(() => setTexts(pickTexts(expense)), [expense]);

  const save = (patch: ExpensePatch) => update.mutate(patch);
  const commitText = (field: TextField) => {
    const value = field === 'note' ? texts[field] : texts[field].trim();
    if (value !== expense[field]) save({ [field]: value });
  };
  const textProps = (field: TextField) => ({
    value: texts[field],
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const value = event.currentTarget.value;
      setTexts((current) => ({ ...current, [field]: value }));
    },
    onBlur: () => commitText(field),
  });

  return (
    <SimpleGrid cols={2} spacing="sm" verticalSpacing="xs">
      <DateInput
        label="支出日期"
        valueFormat="YYYY-MM-DD"
        value={expense.spent_on}
        onChange={(value) => value && value !== expense.spent_on && save({ spent_on: value })}
      />
      <MoneyInput
        label="金额（元）"
        cents={expense.amount_cents}
        onCentsChange={() => undefined}
        onCommit={(cents) => cents !== null && cents !== expense.amount_cents && save({ amount_cents: cents })}
      />
      <TextInput label="商家" {...textProps('merchant')} />
      <TextInput label="摘要" {...textProps('summary')} />
      <CategorySelect label="分类" value={expense.category_id} onChange={(id) => id !== expense.category_id && save({ category_id: id })} clearable />
      <ProjectSelect label="经费项目" value={expense.project_id} onChange={(id) => id !== expense.project_id && save({ project_id: id })} clearable />
      <Autocomplete
        label="付款方式"
        data={PAY_METHODS}
        value={texts.pay_method}
        onChange={(value) => setTexts((current) => ({ ...current, pay_method: value }))}
        onBlur={() => commitText('pay_method')}
      />
      <Switch
        mt={28}
        label="网购"
        checked={expense.is_online}
        onChange={(event) => save({ is_online: event.currentTarget.checked })}
      />
      <Textarea label="备注" autosize minRows={2} style={{ gridColumn: '1 / -1' }} {...textProps('note')} />
    </SimpleGrid>
  );
}

function pickTexts(expense: ExpenseDetail): Record<TextField, string> {
  return { merchant: expense.merchant, summary: expense.summary, pay_method: expense.pay_method, note: expense.note };
}
