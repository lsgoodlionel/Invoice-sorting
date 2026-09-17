import { Group, Select, Text } from '@mantine/core';
import { DateInput } from '@mantine/dates';
import type { ReactNode } from 'react';
import type { DateBasis } from '../../api/types';
import { ALL_DATES_LABEL, customPeriod, isValidDate, type DateRange, type Period } from '../../lib/period';
import { DATE_BASIS_OPTIONS, isDateBasis } from '../../lib/status';
import './period.css';

interface PeriodRangeTextProps {
  period: Period;
  /** 页面实际使用的起止日期（清单页可缺省表示不限） */
  range: Partial<DateRange>;
  onPeriodChange: (period: Period) => void;
  dateBasis: DateBasis;
  onDateBasisChange: (basis: DateBasis) => void;
  /** 口径后的动词，如“统计” */
  verb?: string;
  /** 行尾补充说明，如数据起始月份 */
  hint?: ReactNode;
}

const BASIS_DATA = DATE_BASIS_OPTIONS.map((option) => ({ ...option }));

/** 仅完整的 YYYY-MM-DD 才提交，避免输入过程中的半截日期触发查询。 */
const parseFullDate = (text: string): string | null => {
  const trimmed = text.trim();
  return isValidDate(trimmed) ? trimmed : null;
};

interface BoundInputProps {
  label: string;
  value: string | undefined;
  placeholder: string;
  onChange: (value: string | null) => void;
}

function BoundInput({ label, value, placeholder, onChange }: BoundInputProps) {
  return (
    <DateInput
      aria-label={label}
      title={`${label}：可输入 YYYY-MM-DD 或点击选择`}
      className="period-inline period-date"
      variant="unstyled"
      size="sm"
      valueFormat="YYYY-MM-DD"
      dateParser={parseFullDate}
      placeholder={placeholder}
      value={value ?? null}
      onChange={onChange}
      popoverProps={{ position: 'bottom-start' }}
    />
  );
}

/** 标题下方的区间说明：按 [口径▾] 统计 · [起始] 至 [结束]，日期可直接输入或点选。 */
export function PeriodRangeText({ period, range, onPeriodChange, dateBasis, onDateBasisChange, verb, hint }: PeriodRangeTextProps) {
  const isAll = period.preset === 'all';
  const placeholder = isAll ? '不限' : '选择日期';
  return (
    <Group gap={4} wrap="wrap" align="center" className="period-range num" role="group" aria-label="日期区间">
      <Text span size="sm" c="dimmed">按</Text>
      <Select
        aria-label="日期口径"
        className="period-inline period-basis"
        variant="unstyled"
        size="sm"
        data={BASIS_DATA}
        value={dateBasis}
        allowDeselect={false}
        comboboxProps={{ width: 110, position: 'bottom-start' }}
        onChange={(value) => {
          if (isDateBasis(value)) onDateBasisChange(value);
        }}
      />
      <Text span size="sm" c="dimmed">{verb ? `${verb} · ` : '· '}</Text>
      {isAll && <Text span size="sm" c="dimmed">{ALL_DATES_LABEL}</Text>}
      <BoundInput label="起始日期" value={range.start} placeholder={placeholder} onChange={(start) => onPeriodChange(customPeriod(start, range.end))} />
      <Text span size="sm" c="dimmed">至</Text>
      <BoundInput label="结束日期" value={range.end} placeholder={placeholder} onChange={(end) => onPeriodChange(customPeriod(range.start, end))} />
      {hint}
    </Group>
  );
}
