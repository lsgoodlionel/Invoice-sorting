import { Group, Select } from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import type { DateBasis } from '../api/types';
import { isPreset, PERIOD_OPTIONS, type Period } from '../lib/period';
import { DATE_BASIS_OPTIONS, isDateBasis } from '../lib/status';

interface PeriodPickerProps {
  period: Period;
  onPeriodChange: (period: Period) => void;
  dateBasis?: DateBasis;
  onDateBasisChange?: (basis: DateBasis) => void;
}

export function PeriodPicker({ period, onPeriodChange, dateBasis, onDateBasisChange }: PeriodPickerProps) {
  return (
    <Group gap="xs" wrap="nowrap">
      <Select
        aria-label="周期"
        w={110}
        data={PERIOD_OPTIONS.map((option) => ({ ...option }))}
        value={period.preset}
        allowDeselect={false}
        onChange={(value) => {
          if (isPreset(value)) onPeriodChange({ preset: value, start: period.start, end: period.end });
        }}
      />
      {period.preset === 'custom' && (
        <DatePickerInput
          type="range"
          aria-label="自定义区间"
          placeholder="选择起止日期"
          valueFormat="YYYY-MM-DD"
          w={230}
          allowSingleDateInRange
          value={[period.start ?? null, period.end ?? null]}
          onChange={([start, end]) =>
            onPeriodChange({ preset: 'custom', start: start ?? undefined, end: end ?? undefined })
          }
        />
      )}
      {dateBasis && onDateBasisChange && (
        <Select
          aria-label="日期口径"
          w={110}
          data={DATE_BASIS_OPTIONS.map((option) => ({ ...option }))}
          value={dateBasis}
          allowDeselect={false}
          onChange={(value) => {
            if (isDateBasis(value)) onDateBasisChange(value);
          }}
        />
      )}
    </Group>
  );
}
