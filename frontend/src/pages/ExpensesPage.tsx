import { Button, Group, Loader, Stack, Text, Title } from '@mantine/core';
import { useHotkeys } from '@mantine/hooks';
import { IconPlus } from '@tabler/icons-react';
import { useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useExpenseList } from '../api/hooks/expenses';
import { EmptyHint } from '../components/EmptyHint';
import { ExpenseDrawer } from '../components/ExpenseDrawer/ExpenseDrawer';
import { AddToBatchModal } from '../components/expenses/AddToBatchModal';
import { ExpenseFilterBar } from '../components/expenses/ExpenseFilterBar';
import { ExpenseTable } from '../components/expenses/ExpenseTable';
import { SelectionBar } from '../components/expenses/SelectionBar';
import { StatusGroupBar } from '../components/expenses/StatusGroupBar';
import { useExpenseFilters } from '../components/expenses/useExpenseFilters';
import { usePreventFileDrop } from '../components/expenses/useFileDropTarget';
import { useRowUpload } from '../components/expenses/useRowUpload';
import { useQuickAdd } from '../components/QuickAddContext';
import { filtersToQuery, parseOpenExpenseId } from '../lib/expenseFilters';
import { formatCents, sumCents } from '../lib/money';
import { toggleStatus } from '../lib/status';

function toggleId(ids: readonly number[], id: number): number[] {
  return ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id];
}

export function ExpensesPage() {
  const [filters, setFilters] = useExpenseFilters();
  const query = useMemo(() => filtersToQuery(filters), [filters]);
  const { data, isLoading } = useExpenseList(query);
  const { openQuickAdd } = useQuickAdd();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [searchParams] = useSearchParams();
  const [openId, setOpenId] = useState<number | null>(() => parseOpenExpenseId(searchParams));
  const [isBatchOpen, setBatchOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const uploadToRow = useRowUpload();
  usePreventFileDrop();

  const items = data?.items ?? [];
  const selectedItems = items.filter((item) => selectedIds.includes(item.id));
  const visibleSelectedIds = selectedItems.map((item) => item.id);

  useHotkeys([
    ['/', () => searchRef.current?.focus()],
    ['b', () => visibleSelectedIds.length > 0 && setBatchOpen(true)],
  ]);

  return (
    <Stack gap="md" className="page">
      <Group justify="space-between" align="flex-end" wrap="nowrap">
        <div>
          <Title order={1} className="page-title">清单</Title>
          <Text size="sm" c="dimmed" className="num">
            共 {data?.total ?? 0} 条 · {formatCents(data?.total_cents ?? 0)}
          </Text>
        </div>
        <Button variant="outline" leftSection={<IconPlus size={14} />} onClick={openQuickAdd}>
          记一笔
        </Button>
      </Group>
      <ExpenseFilterBar ref={searchRef} filters={filters} onChange={setFilters} />
      <StatusGroupBar
        counts={data?.status_counts ?? {}}
        selected={filters.statuses}
        onToggle={(status) => setFilters({ statuses: toggleStatus(filters.statuses, status) })}
      />
      {isLoading && <Loader size="sm" />}
      {!isLoading && items.length === 0 && (
        <EmptyHint
          title="这里还没有记录"
          description="把发票、订单截图拖进收集页即可自动建账；也可以按 N 先记一笔，发票到了会自动匹配。"
          action={<Button component={Link} to="/collect" variant="outline">去收集页</Button>}
        />
      )}
      {items.length > 0 && (
        <ExpenseTable
          items={items}
          selectedIds={selectedIds}
          onToggle={(id) => setSelectedIds((ids) => toggleId(ids, id))}
          onToggleAll={(checked) => setSelectedIds(checked ? items.map((item) => item.id) : [])}
          onOpen={setOpenId}
          onDropFiles={uploadToRow}
        />
      )}
      {visibleSelectedIds.length > 0 && (
        <SelectionBar
          count={visibleSelectedIds.length}
          totalCents={sumCents(selectedItems.map((item) => item.amount_cents))}
          onAddToBatch={() => setBatchOpen(true)}
          onClear={() => setSelectedIds([])}
        />
      )}
      <AddToBatchModal
        opened={isBatchOpen}
        expenseIds={visibleSelectedIds}
        onClose={() => setBatchOpen(false)}
        onDone={() => {
          setBatchOpen(false);
          setSelectedIds([]);
        }}
      />
      <ExpenseDrawer expenseId={openId} onClose={() => setOpenId(null)} />
    </Stack>
  );
}
