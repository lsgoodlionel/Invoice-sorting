import { SimpleGrid, Textarea, TextInput } from '@mantine/core';
import { useEffect, useState } from 'react';
import { useUpdateBatch } from '../../api/hooks/batches';
import type { BatchDetail } from '../../api/types';
import { ProjectSelect } from '../ProjectSelect';

export function BatchInfoForm({ batch }: { batch: BatchDetail }) {
  const update = useUpdateBatch(batch.id);
  const [name, setName] = useState(batch.name);
  const [note, setNote] = useState(batch.note);

  useEffect(() => {
    setName(batch.name);
    setNote(batch.note);
  }, [batch.name, batch.note]);

  return (
    <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm" verticalSpacing="xs">
      <TextInput
        label="批次名称"
        value={name}
        onChange={(e) => setName(e.currentTarget.value)}
        onBlur={() => name.trim() && name.trim() !== batch.name && update.mutate({ name: name.trim() })}
      />
      <ProjectSelect label="经费项目" clearable value={batch.project_id} onChange={(id) => id !== batch.project_id && update.mutate({ project_id: id })} />
      <Textarea
        label="备注"
        autosize
        minRows={1}
        style={{ gridColumn: '1 / -1' }}
        value={note}
        onChange={(e) => setNote(e.currentTarget.value)}
        onBlur={() => note !== batch.note && update.mutate({ note })}
      />
    </SimpleGrid>
  );
}
