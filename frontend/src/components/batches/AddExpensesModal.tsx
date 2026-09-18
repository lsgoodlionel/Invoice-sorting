import { Button, Group, Loader, Modal, ScrollArea, Stack, Text } from '@mantine/core';
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { useUnbatchedExpenses } from '../../api/hooks/expenses';
import type { Batch, ExpenseSummary } from '../../api/types';
import {
  DEFAULT_CANDIDATE_FILTERS,
  buildCandidateQuery,
  filterBatchCandidates,
  hasActiveFilters,
  type CandidateFilters,
} from '../../lib/batchCandidates';
import { sumCents } from '../../lib/money';
import { EmptyHint } from '../EmptyHint';
import { AddExpensesFooter } from './AddExpensesFooter';
import { CandidateFilterBar } from './CandidateFilterBar';
import { CandidateResultBar } from './CandidateResultBar';
import { CandidateTable } from './CandidateTable';
import { useAddToBatch } from './useAddToBatch';
import { useCandidateSelection } from './useCandidateSelection';

interface AddExpensesModalProps {
  batch: Pick<Batch, 'id' | 'name' | 'project_id' | 'project_name'>;
  opened: boolean;
  onClose: () => void;
}

const TABLE_MAX_HEIGHT = 380;
const NO_MATCH_HINT = '没有符合筛选条件的记录。';

/** 空结果时的提示：无任何筛选 → 去收集页；仅批次项目限定 → 提示显示全部项目；否则 → 无匹配。 */
type EmptyState = { kind: 'collect' } | { kind: 'text'; text: string };

function emptyState(filters: CandidateFilters, batch: AddExpensesModalProps['batch']): EmptyState {
  if (hasActiveFilters(filters)) return { kind: 'text', text: NO_MATCH_HINT };
  const isProjectLimited = batch.project_id !== null && !filters.showAllProjects;
  if (!isProjectLimited) return { kind: 'collect' };
  return { kind: 'text', text: `「${batch.project_name ?? '该项目'}」下没有未分批记录，可打开“显示全部项目”。` };
}

interface BodyProps {
  isLoading: boolean;
  visible: readonly ExpenseSummary[];
  empty: EmptyState;
  selectedIds: readonly number[];
  onSelect: (ids: readonly number[], checked: boolean) => void;
  onLeave: () => void;
}

function AddExpensesBody({ isLoading, visible, empty, selectedIds, onSelect, onLeave }: BodyProps) {
  if (isLoading) return <Group justify="center" py="xl"><Loader size="sm" /></Group>;
  if (visible.length === 0 && empty.kind === 'collect') {
    return (
      <EmptyHint
        title="没有未分批的记录，先去收集页导入发票"
        action={<Button component={Link} to="/collect" variant="outline" onClick={onLeave}>去收集页</Button>}
      />
    );
  }
  if (visible.length === 0) return <Text size="sm" c="dimmed" py="md">{empty.kind === 'text' ? empty.text : ''}</Text>;
  const visibleIds = visible.map((expense) => expense.id);
  return (
    <Stack gap={6}>
      <CandidateResultBar
        count={visible.length}
        totalCents={sumCents(visible.map((expense) => expense.amount_cents))}
        checkedCount={selectedIds.length}
        onToggleAll={(checked) => onSelect(visibleIds, checked)}
      />
      <ScrollArea.Autosize mah={TABLE_MAX_HEIGHT} type="auto">
        <CandidateTable
          expenses={visible}
          selectedIds={selectedIds}
          onToggle={(id) => onSelect([id], !selectedIds.includes(id))}
          onToggleAll={onSelect}
        />
      </ScrollArea.Autosize>
    </Stack>
  );
}

/** 从批次详情按周期/分类/项目/状态/凭证筛选未分批记录（排除作废）并加入批次。筛选为弹窗内部状态。 */
export function AddExpensesModal({ batch, opened, onClose }: AddExpensesModalProps) {
  const [filters, setFilters] = useState<CandidateFilters>(DEFAULT_CANDIDATE_FILTERS);
  const query = buildCandidateQuery(filters, batch.project_id);
  const { data = [], isLoading, isPlaceholderData } = useUnbatchedExpenses(query, opened);
  const visible = filterBatchCandidates(data, filters);
  const selection = useCandidateSelection(visible.map((expense) => expense.id), !isLoading && !isPlaceholderData);
  const addToBatch = useAddToBatch(onClose);
  const { reset } = addToBatch;
  const { reset: resetSelection } = selection;

  useEffect(() => {
    if (!opened) return;
    setFilters(DEFAULT_CANDIDATE_FILTERS);
    resetSelection();
    reset();
  }, [opened, batch.id, reset, resetSelection]);

  const selected = visible.filter((expense) => selection.selectedIds.includes(expense.id));
  const patchFilters = (patch: Partial<CandidateFilters>) => {
    reset();
    setFilters((current) => ({ ...current, ...patch }));
  };
  const select = (ids: readonly number[], checked: boolean) => {
    reset();
    selection.toggle(ids, checked);
  };
  const note = selection.droppedCount > 0 ? `筛选变化，已取消 ${selection.droppedCount} 条不在结果中的勾选` : undefined;

  return (
    <Modal opened={opened} onClose={onClose} title={`添加记录到「${batch.name}」`} size="xl">
      <Stack gap="sm">
        <CandidateFilterBar filters={filters} onChange={patchFilters} batchProjectName={batch.project_name} hasProjectLimit={batch.project_id !== null} />
        <AddExpensesBody isLoading={isLoading} visible={visible} empty={emptyState(filters, batch)}
          selectedIds={selection.selectedIds} onSelect={select} onLeave={onClose} />
        <AddExpensesFooter
          count={selected.length}
          totalCents={sumCents(selected.map((expense) => expense.amount_cents))}
          conflict={addToBatch.conflict}
          isPending={addToBatch.isPending}
          note={note}
          onClose={onClose}
          onSubmit={() => addToBatch.add(batch.id, selected.map((expense) => expense.id))}
          onConfirm={addToBatch.confirm}
        />
      </Stack>
    </Modal>
  );
}
