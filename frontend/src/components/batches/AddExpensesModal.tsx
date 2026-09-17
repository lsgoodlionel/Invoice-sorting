import { Button, Group, Loader, Modal, ScrollArea, Stack, Switch, Text, TextInput } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { useUnbatchedExpenses } from '../../api/hooks/expenses';
import type { Batch, ExpenseSummary } from '../../api/types';
import { filterBatchCandidates, selectableExpenses } from '../../lib/batchCandidates';
import { sumCents } from '../../lib/money';
import { EmptyHint } from '../EmptyHint';
import { AddExpensesFooter } from './AddExpensesFooter';
import { CandidateTable } from './CandidateTable';
import { useAddToBatch } from './useAddToBatch';

interface AddExpensesModalProps {
  batch: Pick<Batch, 'id' | 'name' | 'project_id' | 'project_name'>;
  opened: boolean;
  onClose: () => void;
}

const TABLE_MAX_HEIGHT = 420;

function toggleIds(ids: readonly number[], targets: readonly number[], checked: boolean): number[] {
  const rest = ids.filter((id) => !targets.includes(id));
  return checked ? [...rest, ...targets] : rest;
}

function noMatchHint(projectName: string | null, isHiddenByProject: boolean): string {
  return isHiddenByProject ? `「${projectName ?? '该项目'}」下没有未分批记录，可打开“显示全部项目”。` : '没有匹配的记录。';
}

interface BodyProps {
  isLoading: boolean;
  hasCandidates: boolean;
  visible: readonly ExpenseSummary[];
  emptyHint: string;
  selectedIds: readonly number[];
  onSelect: (ids: readonly number[], checked: boolean) => void;
  onLeave: () => void;
}

function AddExpensesBody({ isLoading, hasCandidates, visible, emptyHint, selectedIds, onSelect, onLeave }: BodyProps) {
  if (isLoading) return <Group justify="center" py="xl"><Loader size="sm" /></Group>;
  if (!hasCandidates) {
    return (
      <EmptyHint
        title="没有未分批的记录，先去收集页导入发票"
        action={<Button component={Link} to="/collect" variant="outline" onClick={onLeave}>去收集页</Button>}
      />
    );
  }
  if (visible.length === 0) return <Text size="sm" c="dimmed" py="md">{emptyHint}</Text>;
  return (
    <ScrollArea.Autosize mah={TABLE_MAX_HEIGHT} type="auto">
      <CandidateTable
        expenses={visible}
        selectedIds={selectedIds}
        onToggle={(id) => onSelect([id], !selectedIds.includes(id))}
        onToggleAll={onSelect}
      />
    </ScrollArea.Autosize>
  );
}

/** 从批次详情直接挑选未分批记录（排除作废）加入批次。 */
export function AddExpensesModal({ batch, opened, onClose }: AddExpensesModalProps) {
  const [search, setSearch] = useState('');
  const [showAllProjects, setShowAllProjects] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const { data = [], isLoading } = useUnbatchedExpenses(opened);
  const addToBatch = useAddToBatch(onClose);
  const { reset } = addToBatch;

  useEffect(() => {
    if (!opened) return;
    setSearch('');
    setShowAllProjects(false);
    setSelectedIds([]);
    reset();
  }, [opened, batch.id, reset]);

  const candidates = selectableExpenses(data);
  const visible = filterBatchCandidates(candidates, { projectId: batch.project_id, showAllProjects, search });
  const selected = candidates.filter((expense) => selectedIds.includes(expense.id));
  const hasProjectLimit = batch.project_id !== null;
  const emptyHint = noMatchHint(batch.project_name, !search.trim() && hasProjectLimit && !showAllProjects);

  const select = (ids: readonly number[], checked: boolean) => {
    reset();
    setSelectedIds((current) => toggleIds(current, ids, checked));
  };

  return (
    <Modal opened={opened} onClose={onClose} title={`添加记录到「${batch.name}」`} size="xl">
      <Stack gap="sm">
        <Group gap="md" wrap="wrap">
          <TextInput aria-label="搜索记录" placeholder="搜索商家 / 摘要 / 发票号" leftSection={<IconSearch size={14} />}
            style={{ flex: 1, minWidth: 200 }} value={search} onChange={(event) => setSearch(event.currentTarget.value)} />
          {hasProjectLimit && (
            <Switch label="显示全部项目" checked={showAllProjects} onChange={(event) => setShowAllProjects(event.currentTarget.checked)} />
          )}
        </Group>
        <AddExpensesBody isLoading={isLoading} hasCandidates={candidates.length > 0} visible={visible} emptyHint={emptyHint}
          selectedIds={selectedIds} onSelect={select} onLeave={onClose} />
        <AddExpensesFooter
          count={selected.length}
          totalCents={sumCents(selected.map((expense) => expense.amount_cents))}
          conflict={addToBatch.conflict}
          isPending={addToBatch.isPending}
          onClose={onClose}
          onSubmit={() => addToBatch.add(batch.id, selected.map((expense) => expense.id))}
          onConfirm={addToBatch.confirm}
        />
      </Stack>
    </Modal>
  );
}
