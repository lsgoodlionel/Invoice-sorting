import { Select, type MantineSize } from '@mantine/core';
import { CURRENCY_OPTIONS, currencySymbol, isForeignCurrency } from '../lib/money';
import { MoneyInput } from './MoneyInput';

interface CurrencyAmountInputsProps {
  currency: string;
  originalCents: number | null;
  onCurrencyChange: (currency: string) => void;
  /** 原币金额输入合法时回调（草稿场景） */
  onOriginalChange?: (cents: number | null) => void;
  /** 原币金额失焦时回调（自动保存场景） */
  onOriginalCommit?: (cents: number | null) => void;
  size?: MantineSize;
  disabled?: boolean;
}

/** 币种下拉 + 原币金额；人民币时隐藏原币金额。 */
export function CurrencyAmountInputs(props: CurrencyAmountInputsProps) {
  const { currency, originalCents, onCurrencyChange, onOriginalChange, onOriginalCommit, size, disabled } = props;
  return (
    <>
      <Select
        size={size}
        label="币种"
        aria-label="币种"
        data={CURRENCY_OPTIONS}
        value={currency || 'CNY'}
        allowDeselect={false}
        disabled={disabled}
        onChange={(value) => value && value !== currency && onCurrencyChange(value)}
      />
      {isForeignCurrency(currency) && (
        <MoneyInput
          size={size}
          label="原币金额"
          aria-label="原币金额"
          leftSection={currencySymbol(currency)}
          leftSectionWidth={44}
          cents={originalCents}
          disabled={disabled}
          onCentsChange={(cents) => onOriginalChange?.(cents)}
          onCommit={onOriginalCommit}
        />
      )}
    </>
  );
}
