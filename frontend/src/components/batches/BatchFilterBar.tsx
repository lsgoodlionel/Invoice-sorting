import { SegmentedControl, Stack } from '@mantine/core';
import {
  BATCH_DATE_BASIS_OPTIONS,
  BATCH_STATUS_FILTER_OPTIONS,
  isBatchStatusFilter,
  type BatchFilters,
} from '../../lib/batchFilters';
import { resolvePeriod } from '../../lib/period';
import { PeriodPresetBar } from '../period/PeriodPresetBar';
import { PeriodRangeText } from '../period/PeriodRangeText';

interface BatchFilterBarProps {
  filters: BatchFilters;
  onChange: (patch: Partial<BatchFilters>) => void;
}

const STATUS_DATA = BATCH_STATUS_FILTER_OPTIONS.map((option) => ({ ...option }));

/** 批次列表上方：状态分段选择 + 周期（创建/外发/到账日期口径）。 */
export function BatchFilterBar({ filters, onChange }: BatchFilterBarProps) {
  return (
    <Stack gap={4}>
      <SegmentedControl
        aria-label="批次状态"
        size="xs"
        fullWidth
        data={STATUS_DATA}
        value={filters.status}
        onChange={(value) => {
          if (isBatchStatusFilter(value)) onChange({ status: value });
        }}
      />
      <PeriodRangeText
        period={filters.period}
        range={resolvePeriod(filters.period)}
        onPeriodChange={(period) => onChange({ period })}
        dateBasis={filters.basis}
        basisOptions={BATCH_DATE_BASIS_OPTIONS}
        onDateBasisChange={(basis) => onChange({ basis })}
      />
      <PeriodPresetBar includeAll value={filters.period.preset} onSelect={(period) => onChange({ period })} />
    </Stack>
  );
}
