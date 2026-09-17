import { Button, ColorInput, Group, Modal, Stack, Table, TagsInput, Text, Textarea, TextInput } from '@mantine/core';
import { modals } from '@mantine/modals';
import { useEffect, useState } from 'react';
import { useArchiveCategory, useCategories, useSaveCategory } from '../../api/hooks/settings';
import type { Category, CategoryInput } from '../../api/types';
import { CategoryDot } from '../CategoryDot';

const DEFAULT_COLOR = '#1F5F4A';
const emptyInput = (): CategoryInput => ({ name: '', color: DEFAULT_COLOR, keywords: [], route_hint: '' });

function CategoryModal({ editing, onClose }: { editing: Category | 'new' | null; onClose: () => void }) {
  const [input, setInput] = useState<CategoryInput>(emptyInput);
  const save = useSaveCategory();
  useEffect(() => {
    if (editing === 'new') setInput(emptyInput());
    else if (editing) setInput({ name: editing.name, color: editing.color, keywords: editing.keywords, route_hint: editing.route_hint });
  }, [editing]);
  const patch = (p: Partial<CategoryInput>) => setInput((current) => ({ ...current, ...p }));
  const submit = () =>
    save.mutate({ id: editing === 'new' || !editing ? null : editing.id, input: { ...input, name: input.name.trim() } }, { onSuccess: onClose });
  return (
    <Modal opened={editing !== null} onClose={onClose} title={editing === 'new' ? '新增分类' : '编辑分类'}>
      <Stack gap="sm">
        <TextInput label="名称" required value={input.name} onChange={(e) => patch({ name: e.currentTarget.value })} />
        <ColorInput label="颜色" value={input.color} onChange={(color) => patch({ color })} />
        <TagsInput label="识别关键词" description="回车添加" value={input.keywords} onChange={(keywords) => patch({ keywords })} />
        <Textarea label="办理路径" autosize minRows={3} value={input.route_hint} onChange={(e) => patch({ route_hint: e.currentTarget.value })} />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>取消</Button>
          <Button variant="filled" disabled={!input.name.trim()} loading={save.isPending} onClick={submit}>保存</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

export function CategoryManager() {
  const { data = [] } = useCategories();
  const archive = useArchiveCategory();
  const [editing, setEditing] = useState<Category | 'new' | null>(null);
  const confirmArchive = (category: Category) =>
    modals.openConfirmModal({
      title: '归档分类',
      children: <Text size="sm">「{category.name}」归档后不再出现在选择列表，已有记录不受影响。</Text>,
      labels: { confirm: '归档', cancel: '取消' },
      onConfirm: () => archive.mutate(category.id),
    });
  return (
    <Stack gap="xs">
      <Group justify="flex-end"><Button size="xs" variant="outline" onClick={() => setEditing('new')}>新增分类</Button></Group>
      <div className="table-scroll">
        <Table className="ledger-table" miw={640}>
          <Table.Thead><Table.Tr><Table.Th>名称</Table.Th><Table.Th>关键词</Table.Th><Table.Th>办理路径</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.map((category) => (
              <Table.Tr key={category.id} style={{ opacity: category.archived ? 0.5 : 1 }}>
                <Table.Td><CategoryDot color={category.color} name={category.name + (category.archived ? '（已归档）' : '')} /></Table.Td>
                <Table.Td><Text size="xs" c="dimmed" truncate maw={260}>{category.keywords.join('、')}</Text></Table.Td>
                <Table.Td><Text size="xs" c="dimmed" truncate maw={200}>{category.route_hint}</Text></Table.Td>
                <Table.Td>
                  <Group gap={4} justify="flex-end" wrap="nowrap">
                    <Button size="compact-xs" variant="subtle" onClick={() => setEditing(category)}>编辑</Button>
                    {!category.archived && <Button size="compact-xs" variant="subtle" color="red" onClick={() => confirmArchive(category)}>归档</Button>}
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </div>
      <CategoryModal editing={editing} onClose={() => setEditing(null)} />
    </Stack>
  );
}
