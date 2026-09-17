import { Switch } from '@mantine/core';
import { useUpdateExpense } from '../../api/hooks/expenses';
import type { ExpenseDetail } from '../../api/types';
import { DEFAULT_CURRENCY } from '../../lib/money';
import { CurrencyAmountInputs } from '../CurrencyAmountInputs';

/** 免发票（境外消费）开关、币种与原币金额；开关与币种即时保存，原币金额失焦保存。 */
export function ForeignExpenseFields({ expense }: { expense: ExpenseDetail }) {
  const update = useUpdateExpense(expense.id);
  const currency = expense.currency || DEFAULT_CURRENCY;

  const changeCurrency = (next: string) =>
    update.mutate(next === DEFAULT_CURRENCY ? { currency: next, original_amount_cents: null } : { currency: next });

  const commitOriginal = (cents: number | null) => {
    if (cents !== expense.original_amount_cents) update.mutate({ original_amount_cents: cents });
  };

  return (
    <>
      <Switch
        mt={28}
        label="免发票（境外消费）"
        checked={expense.invoice_exempt}
        onChange={(event) => update.mutate({ invoice_exempt: event.currentTarget.checked })}
      />
      <CurrencyAmountInputs
        currency={currency}
        originalCents={expense.original_amount_cents}
        onCurrencyChange={changeCurrency}
        onOriginalCommit={commitOriginal}
      />
    </>
  );
}
