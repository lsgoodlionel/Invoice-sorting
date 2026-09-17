import { Button, Group, TextInput } from '@mantine/core';
import { useDebouncedCallback } from '@mantine/hooks';
import { IconSearch, IconX } from '@tabler/icons-react';
import { forwardRef, useEffect, useState } from 'react';
import type { ExpenseFilters } from '../../lib/expenseFilters';
import { CategorySelect } from '../CategorySelect';
import { PeriodPicker } from '../PeriodPicker';
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

  const hasExtraFilters = filters.batchId !== null || filters.unbatched || filters.missingOnly;

  return (
    <Group gap="xs" wrap="wrap">
      <PeriodPicker
        period={filters.period}
        onPeriodChange={(period) => onChange({ period })}
        dateBasis={filters.dateBasis}
        onDateBasisChange={(dateBasis) => onChange({ dateBasis })}
      />
      <CategorySelect w={130} placeholder="全部分类" clearable value={filters.categoryId} onChange={(categoryId) => onChange({ categoryId })} />
      <ProjectSelect w={150} placeholder="全部项目" clearable value={filters.projectId} onChange={(projectId) => onChange({ projectId })} />
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
          onClick={() => onChange({ batchId: null, unbatched: false, missingOnly: false })}
        >
          {filters.missingOnly ? '仅缺项' : filters.unbatched ? '仅未分批' : `批次 #${filters.batchId}`}
        </Button>
      )}
    </Group>
  );
});
