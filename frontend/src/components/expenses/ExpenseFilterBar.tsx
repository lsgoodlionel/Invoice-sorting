import { Button, Group, Select, Stack, TextInput } from '@mantine/core';
import { useDebouncedCallback } from '@mantine/hooks';
import { IconSearch, IconX } from '@tabler/icons-react';
import { forwardRef, useEffect, useState } from 'react';
import type { ExpenseFilters } from '../../lib/expenseFilters';
import { resolvePeriod } from '../../lib/period';
import { ALL_STATUSES, DEFAULT_VISIBLE_STATUSES } from '../../lib/status';
import { CategorySelect } from '../CategorySelect';
import { PeriodPresetBar } from '../period/PeriodPresetBar';
import { PeriodRangeText } from '../period/PeriodRangeText';
import { ProjectSelect } from '../ProjectSelect';

interface ExpenseFilterBarProps {
  filters: ExpenseFilters;
  onChange: (patch: Partial<ExpenseFilters>) => void;
}

const SEARCH_DEBOUNCE_MS = 300;

export const ExpenseFilterBar = forwardRef<HTMLInputElement, ExpenseFilterBarProps>(function ExpenseFilterBar(
  { filters, onChange },
  searchRef,
) {
  const [search, setSearch] = useState(filters.q);
  const commitSearch = useDebouncedCallback((q: string) => onChange({ q }), SEARCH_DEBOUNCE_MS);

  useEffect(() => setSearch(filters.q), [filters.q]);

  const hasExtraFilters = filters.batchId !== null || filters.unbatched || filters.missingOnly || filters.uncategorized || filters.requiresLabPlatform !== null;
  const statusView = filters.statuses.length === DEFAULT_VISIBLE_STATUSES.length
    && DEFAULT_VISIBLE_STATUSES.every((status) => filters.statuses.includes(status))
    ? 'open'
    : filters.statuses.length === ALL_STATUSES.length && ALL_STATUSES.every((status) => filters.statuses.includes(status))
      ? 'all'
      : filters.statuses.length === 1 && filters.statuses[0] === 'sent'
        ? 'sent'
        : filters.statuses.length === 1 && filters.statuses[0] === 'reimbursed' ? 'reimbursed' : 'custom';

  return (
    <Stack gap={6}>
      <PeriodRangeText
        period={filters.period}
        range={resolvePeriod(filters.period)}
        onPeriodChange={(period) => onChange({ period })}
        dateBasis={filters.dateBasis}
        onDateBasisChange={(dateBasis) => onChange({ dateBasis })}
      />
      <Group gap="xs" wrap="wrap">
        <PeriodPresetBar value={filters.period.preset} onSelect={(period) => onChange({ period })} />
        <CategorySelect w={130} placeholder="全部分类" clearable value={filters.categoryId} onChange={(categoryId) => onChange({ categoryId, uncategorized: false })} />
        <ProjectSelect w={150} placeholder="全部项目" creatable={false} clearable value={filters.projectId} onChange={(projectId) => onChange({ projectId })} />
        <Select
          w={135}
          aria-label="显示状态"
          data={[
            { value: 'open', label: '默认待处理' },
            { value: 'all', label: '全部状态' },
            { value: 'sent', label: '仅已外发' },
            { value: 'reimbursed', label: '仅已到账' },
            { value: 'custom', label: '自定义状态', disabled: true },
          ]}
          value={statusView}
          onChange={(value) => {
            if (value === 'open') onChange({ statuses: [...DEFAULT_VISIBLE_STATUSES] });
            if (value === 'all') onChange({ statuses: [...ALL_STATUSES] });
            if (value === 'sent') onChange({ statuses: ['sent'] });
            if (value === 'reimbursed') onChange({ statuses: ['reimbursed'] });
          }}
        />
        <Select
          w={125}
          aria-label="市内市外"
          placeholder="市内/市外"
          clearable
          data={[{ value: 'local', label: '市内' }, { value: 'nonlocal', label: '市外' }]}
          value={filters.travelScope || null}
          onChange={(value) => onChange({ travelScope: value === 'local' || value === 'nonlocal' ? value : '' })}
        />
        <Select
          w={150}
          aria-label="设备与实验室平台申请"
          placeholder="平台申请"
          clearable
          data={[{ value: 'required', label: '需要平台申请' }, { value: 'not_required', label: '无需平台申请' }]}
          value={filters.requiresLabPlatform === null ? null : filters.requiresLabPlatform ? 'required' : 'not_required'}
          onChange={(value) => onChange({ requiresLabPlatform: value === 'required' ? true : value === 'not_required' ? false : null })}
        />
        <TextInput
          ref={searchRef}
          w={220}
          aria-label="搜索"
          placeholder="搜索商家 / 摘要 / 发票号  /"
          leftSection={<IconSearch size={14} />}
          value={search}
          onChange={(event) => {
            const value = event.currentTarget.value;
            setSearch(value);
            commitSearch(value);
          }}
        />
        {hasExtraFilters && (
          <Button
            size="xs"
            variant="subtle"
            leftSection={<IconX size={12} />}
            onClick={() => onChange({ batchId: null, unbatched: false, missingOnly: false, uncategorized: false, requiresLabPlatform: null })}
          >
            {filters.missingOnly ? '仅缺项' : filters.uncategorized ? '仅未分类' : filters.unbatched ? '仅未分批' : filters.batchId ? `批次 #${filters.batchId}` : '平台申请筛选'}
          </Button>
        )}
      </Group>
    </Stack>
  );
});
