import { TextInput, type TextInputProps } from '@mantine/core';
import { useEffect, useState } from 'react';
import { centsToYuanString, parseYuanToCents } from '../lib/money';

interface MoneyInputProps extends Omit<TextInputProps, 'value' | 'onChange' | 'onBlur'> {
  cents: number | null;
  /** 输入合法时回调分；清空时回调 null */
  onCentsChange: (cents: number | null) => void;
  /** 失焦时回调（用于自动保存） */
  onCommit?: (cents: number | null) => void;
}

export function MoneyInput({ cents, onCentsChange, onCommit, error, ...rest }: MoneyInputProps) {
  const [text, setText] = useState(centsToYuanString(cents));
  const [isInvalid, setIsInvalid] = useState(false);

  useEffect(() => {
    setText((current) => (parseYuanToCents(current) === cents ? current : centsToYuanString(cents)));
  }, [cents]);

  const handleChange = (value: string) => {
    setText(value);
    const parsed = parseYuanToCents(value);
    const invalid = value.trim() !== '' && parsed === null;
    setIsInvalid(invalid);
    if (!invalid) onCentsChange(parsed);
  };

  return (
    <TextInput
      inputMode="decimal"
      leftSection="¥"
      classNames={{ input: 'num' }}
      value={text}
      onChange={(event) => handleChange(event.currentTarget.value)}
      onBlur={() => {
        if (isInvalid) return;
        onCommit?.(parseYuanToCents(text));
      }}
      error={isInvalid ? '金额格式不正确' : error}
      {...rest}
    />
  );
}
