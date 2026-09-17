import { Autocomplete, Button, Group, Modal, Stack, TextInput } from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { useEffect, useState } from 'react';
import { useMarkBatchSent } from '../../api/hooks/batches';
import type { BatchDetail } from '../../api/types';
import { todayInShanghai } from '../../lib/period';

interface SentModalProps {
  batch: BatchDetail;
  opened: boolean;
  onClose: () => void;
}

const SENT_VIA_OPTIONS = ['邮件', '当面', '寄送', '系统预约'];

export function SentModal({ batch, opened, onClose }: SentModalProps) {
  const [form, setForm] = useState({ sentOn: todayInShanghai() as string | null, via: '', receiver: '', externalNo: '' });
  const markSent = useMarkBatchSent(batch.id);

  useEffect(() => {
    if (opened) {
      setForm({ sentOn: batch.sent_on ?? todayInShanghai(), via: batch.sent_via, receiver: batch.receiver, externalNo: batch.external_no });
    }
  }, [opened, batch]);

  const submit = () => {
    if (!form.sentOn) return;
    markSent.mutate(
      { sent_on: form.sentOn, sent_via: form.via, receiver: form.receiver, external_no: form.externalNo },
      { onSuccess: onClose },
    );
  };

  return (
    <Modal opened={opened} onClose={onClose} title="标记已外发">
      <Stack gap="sm">
        <DateInput label="外发日期" required valueFormat="YYYY-MM-DD" value={form.sentOn} onChange={(sentOn) => setForm((f) => ({ ...f, sentOn }))} />
        <Autocomplete label="方式" data={SENT_VIA_OPTIONS} value={form.via} onChange={(via) => setForm((f) => ({ ...f, via }))} />
        <TextInput label="接收人" value={form.receiver} onChange={(e) => { const receiver = e.currentTarget.value; setForm((f) => ({ ...f, receiver })); }} />
        <TextInput label="外部单号" placeholder="预约单号等" value={form.externalNo} onChange={(e) => { const externalNo = e.currentTarget.value; setForm((f) => ({ ...f, externalNo })); }} />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>取消</Button>
          <Button variant="filled" disabled={!form.sentOn} loading={markSent.isPending} onClick={submit}>确认外发</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
