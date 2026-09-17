import { Button, Checkbox, Group, Modal, Radio, ScrollArea, Stack, Text } from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { useEffect, useState } from 'react';
import { useMarkBatchReceived } from '../../api/hooks/batches';
import type { BatchDetail } from '../../api/types';
import { formatCents, sumCents } from '../../lib/money';
import { todayInShanghai } from '../../lib/period';

interface ReceivedModalProps {
  batch: BatchDetail;
  opened: boolean;
  onClose: () => void;
}

export function ReceivedModal({ batch, opened, onClose }: ReceivedModalProps) {
  const [receivedOn, setReceivedOn] = useState<string | null>(todayInShanghai());
  const [scope, setScope] = useState<'all' | 'partial'>('all');
  const [ids, setIds] = useState<string[]>([]);
  const markReceived = useMarkBatchReceived(batch.id);
  const pending = batch.expenses.filter((expense) => expense.status !== 'reimbursed' && expense.status !== 'void');

  useEffect(() => {
    if (!opened) return;
    setReceivedOn(todayInShanghai());
    setScope('all');
    setIds([]);
  }, [opened]);

  const selectedCents = sumCents(pending.filter((e) => ids.includes(String(e.id))).map((e) => e.amount_cents));
  const isValid = Boolean(receivedOn) && (scope === 'all' || ids.length > 0);

  const submit = () => {
    if (!receivedOn) return;
    const payload = scope === 'all' ? { received_on: receivedOn } : { received_on: receivedOn, expense_ids: ids.map(Number) };
    markReceived.mutate(payload, { onSuccess: onClose });
  };

  return (
    <Modal opened={opened} onClose={onClose} title="登记到账">
      <Stack gap="sm">
        <DateInput label="到账日期" required valueFormat="YYYY-MM-DD" value={receivedOn} onChange={setReceivedOn} />
        <Radio.Group label="到账范围" value={scope} onChange={(value) => setScope(value === 'partial' ? 'partial' : 'all')}>
          <Group gap="lg" mt={4}>
            <Radio value="all" label="全部记录" />
            <Radio value="partial" label="勾选部分记录" />
          </Group>
        </Radio.Group>
        {scope === 'partial' && (
          <ScrollArea.Autosize mah={260}>
            <Checkbox.Group value={ids} onChange={setIds}>
              <Stack gap={6}>
                {pending.map((expense) => (
                  <Checkbox
                    key={expense.id}
                    value={String(expense.id)}
                    label={<span className="num">{expense.spent_on} {expense.merchant} {formatCents(expense.amount_cents)}</span>}
                  />
                ))}
              </Stack>
            </Checkbox.Group>
          </ScrollArea.Autosize>
        )}
        {scope === 'partial' && <Text size="sm" className="num">已选 {ids.length} 条 · {formatCents(selectedCents)}</Text>}
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>取消</Button>
          <Button variant="filled" disabled={!isValid} loading={markReceived.isPending} onClick={submit}>确认到账</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
