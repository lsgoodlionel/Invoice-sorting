import { Box, Button, Group, Loader, Stack, Title } from '@mantine/core';
import { IconPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { useBatch, useBatchList } from '../api/hooks/batches';
import { AddExpensesModal } from '../components/batches/AddExpensesModal';
import { BatchDetailPanel } from '../components/batches/BatchDetailPanel';
import { BatchList } from '../components/batches/BatchList';
import { NewBatchModal } from '../components/batches/NewBatchModal';
import { EmptyHint } from '../components/EmptyHint';
import { ExpenseDrawer } from '../components/ExpenseDrawer/ExpenseDrawer';

const LIST_WIDTH = 280;

export function BatchesPage() {
  const [params, setParams] = useSearchParams();
  const { data: batches = [], isLoading } = useBatchList();
  const [isNewOpen, setNewOpen] = useState(false);
  const [openExpenseId, setOpenExpenseId] = useState<number | null>(null);
  const [addingBatchId, setAddingBatchId] = useState<number | null>(null);

  const rawId = Number(params.get('id'));
  const selectedId = Number.isInteger(rawId) && rawId > 0 ? rawId : (batches[0]?.id ?? null);
  const { data: batch } = useBatch(selectedId);
  const select = (id: number | null) => setParams(id === null ? {} : { id: String(id) }, { replace: true });
  // 新建的批次一定为空：选中后直接打开“添加记录”，省去一步
  const handleCreated = (id: number) => {
    select(id);
    setAddingBatchId(id);
  };

  return (
    <Stack gap="md" className="page">
      <Group justify="space-between">
        <Title order={1} className="page-title">批次</Title>
        <Button variant="outline" leftSection={<IconPlus size={14} />} onClick={() => setNewOpen(true)}>新建批次</Button>
      </Group>
      <Group align="flex-start" gap="lg" wrap="nowrap">
        <Box w={LIST_WIDTH} className="batch-list">
          {isLoading ? <Loader size="sm" m="sm" /> : <BatchList batches={batches} selectedId={selectedId} onSelect={select} />}
        </Box>
        <Box style={{ flex: 1, minWidth: 0 }}>
          {batch && batch.id === selectedId ? (
            <BatchDetailPanel batch={batch} onOpenExpense={setOpenExpenseId} onDeleted={() => select(null)} onAddExpenses={() => setAddingBatchId(batch.id)} />
          ) : (
            !isLoading && batches.length === 0 && (
              <EmptyHint title="选择或新建一个批次" description="批次是一次外送给财务的资料集合：勾选记录 → 打包 → 标记外发 → 登记到账。" />
            )
          )}
        </Box>
      </Group>
      <NewBatchModal opened={isNewOpen} onClose={() => setNewOpen(false)} onCreated={handleCreated} />
      {batch && <AddExpensesModal batch={batch} opened={addingBatchId === batch.id} onClose={() => setAddingBatchId(null)} />}
      <ExpenseDrawer expenseId={openExpenseId} onClose={() => setOpenExpenseId(null)} />
    </Stack>
  );
}
