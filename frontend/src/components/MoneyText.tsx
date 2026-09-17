import { Text, type TextProps } from '@mantine/core';
import { formatCents } from '../lib/money';

interface MoneyTextProps extends TextProps {
  cents: number | null | undefined;
  symbol?: boolean;
}

export function MoneyText({ cents, symbol = true, className, ...rest }: MoneyTextProps) {
  return (
    <Text component="span" inherit className={['num', className].filter(Boolean).join(' ')} {...rest}>
      {formatCents(cents, { symbol })}
    </Text>
  );
}
