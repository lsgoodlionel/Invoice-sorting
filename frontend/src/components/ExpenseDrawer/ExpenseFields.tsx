import { Autocomplete, NumberInput, Select, SimpleGrid, Switch, Textarea, TextInput } from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { useEffect, useState } from 'react';
import { useUpdateExpense } from '../../api/hooks/expenses';
import type { ExpenseDetail, ExpensePatch } from '../../api/types';
import { CategorySelect } from '../CategorySelect';
import { MoneyInput } from '../MoneyInput';
import { ProjectSelect } from '../ProjectSelect';
import { ForeignExpenseFields } from './ForeignExpenseFields';

const PAY_METHODS = ['微信', '支付宝', '银行卡', '公务卡', '现金', '对公转账'];

type TextField = 'merchant' | 'summary' | 'item_name' | 'pay_method' | 'note';

/** 可编辑字段：文本失焦保存，选择类即时保存；只提交变化的字段。 */
export function ExpenseFields({ expense }: { expense: ExpenseDetail }) {
  const update = useUpdateExpense(expense.id);
  const [texts, setTexts] = useState<Record<TextField, string>>(() => pickTexts(expense));

  useEffect(() => setTexts(pickTexts(expense)), [expense]);

  const save = (patch: ExpensePatch) => update.mutate(patch);
  const commitText = (field: TextField) => {
    const value = field === 'note' ? texts[field] : texts[field].trim();
    const original = field === 'item_name' ? (expense.item_name_manual ?? '') : expense[field];
    if (value !== original) save({ [field]: value });
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
        label="业务发生日期"
        valueFormat="YYYY-MM-DD"
        value={expense.spent_on}
        onChange={(value) => value && value !== expense.spent_on && save({ spent_on: value })}
      />
      <MoneyInput
        label="人民币金额（元）"
        cents={expense.amount_cents}
        onCentsChange={() => undefined}
        onCommit={(cents) => cents !== null && cents !== expense.amount_cents && save({ amount_cents: cents })}
      />
      <TextInput label="商家" {...textProps('merchant')} />
      <TextInput label="摘要" {...textProps('summary')} />
      <TextInput label="名称" description="用于清单和导出；留空时自动取摘要或发票商品名称" {...textProps('item_name')} />
      <MoneyInput
        label="单价（元）"
        cents={expense.unit_price_cents ?? null}
        onCentsChange={() => undefined}
        onCommit={(cents) => cents !== (expense.unit_price_cents ?? null) && save({ unit_price_cents: cents })}
      />
      <NumberInput
        label="数量"
        min={1}
        max={100}
        allowDecimal={false}
        value={expense.quantity ?? ''}
        onChange={(value) => {
          const quantity = typeof value === 'number' ? value : null;
          if (quantity !== (expense.quantity ?? null)) save({ quantity });
        }}
      />
      <CategorySelect label="分类" value={expense.category_id} onChange={(id) => id !== expense.category_id && save({ category_id: id })} clearable />
      <ProjectSelect label="经费项目" value={expense.project_id} onChange={(id) => id !== expense.project_id && save({ project_id: id })} clearable />
      <Select
        label="市内/市外"
        description={expense.travel_scope_manual ? '已手工设置' : '根据设置中的本地地区自动识别'}
        data={[
          { value: '', label: '自动识别' },
          { value: 'local', label: '市内' },
          { value: 'nonlocal', label: '市外' },
        ]}
        value={expense.travel_scope_manual ? expense.travel_scope : ''}
        onChange={(value) => save({ travel_scope: value === 'local' || value === 'nonlocal' ? value : '' })}
      />
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
      <ForeignExpenseFields expense={expense} />
      <Textarea label="备注" autosize minRows={2} style={{ gridColumn: '1 / -1' }} {...textProps('note')} />
    </SimpleGrid>
  );
}

function pickTexts(expense: ExpenseDetail): Record<TextField, string> {
  return { merchant: expense.merchant, summary: expense.summary, item_name: expense.item_name_manual ?? '', pay_method: expense.pay_method, note: expense.note };
}
