import { Badge, Button, Group, Modal, Stack, Table, Text, TextInput } from '@mantine/core';
import { useEffect, useState } from 'react';
import { useDeactivateProject, useProjects, useSaveProject } from '../../api/hooks/settings';
import type { Project, ProjectInput } from '../../api/types';

const emptyInput = (): ProjectInput => ({ code: '', name: '', owner: '' });

function ProjectModal({ editing, onClose }: { editing: Project | 'new' | null; onClose: () => void }) {
  const [input, setInput] = useState<ProjectInput>(emptyInput);
  const save = useSaveProject();
  useEffect(() => {
    if (editing === 'new') setInput(emptyInput());
    else if (editing) setInput({ code: editing.code, name: editing.name, owner: editing.owner });
  }, [editing]);
  const patch = (p: Partial<ProjectInput>) => setInput((current) => ({ ...current, ...p }));
  const submit = () =>
    save.mutate({ id: editing === 'new' || !editing ? null : editing.id, input: { ...input, name: input.name.trim() } }, { onSuccess: onClose });
  return (
    <Modal opened={editing !== null} onClose={onClose} title={editing === 'new' ? '新增经费项目' : '编辑经费项目'}>
      <Stack gap="sm">
        <TextInput label="经费号" value={input.code} onChange={(e) => patch({ code: e.currentTarget.value })} />
        <TextInput label="名称" required value={input.name} onChange={(e) => patch({ name: e.currentTarget.value })} />
        <TextInput label="负责人" value={input.owner} onChange={(e) => patch({ owner: e.currentTarget.value })} />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>取消</Button>
          <Button variant="filled" disabled={!input.name.trim()} loading={save.isPending} onClick={submit}>保存</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

export function ProjectManager() {
  const { data = [] } = useProjects();
  const deactivate = useDeactivateProject();
  const save = useSaveProject();
  const [editing, setEditing] = useState<Project | 'new' | null>(null);
  return (
    <Stack gap="xs">
      <Group justify="flex-end"><Button size="xs" variant="outline" onClick={() => setEditing('new')}>新增项目</Button></Group>
      {data.length === 0 ? (
        <Text size="sm" c="dimmed">还没有经费项目。项目可用于筛选与批次限定。</Text>
      ) : (
        <Table className="ledger-table">
          <Table.Thead><Table.Tr><Table.Th>经费号</Table.Th><Table.Th>名称</Table.Th><Table.Th>负责人</Table.Th><Table.Th>状态</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.map((project) => (
              <Table.Tr key={project.id}>
                <Table.Td className="num">{project.code}</Table.Td>
                <Table.Td>{project.name}</Table.Td>
                <Table.Td>{project.owner}</Table.Td>
                <Table.Td><Badge size="sm" variant="light" color={project.active ? 'ink' : 'gray'}>{project.active ? '启用' : '停用'}</Badge></Table.Td>
                <Table.Td>
                  <Group gap={4} justify="flex-end" wrap="nowrap">
                    <Button size="compact-xs" variant="subtle" onClick={() => setEditing(project)}>编辑</Button>
                    {project.active ? (
                      <Button size="compact-xs" variant="subtle" color="red" onClick={() => deactivate.mutate(project.id)}>停用</Button>
                    ) : (
                      <Button size="compact-xs" variant="subtle" onClick={() => save.mutate({ id: project.id, input: { name: project.name, active: true } })}>启用</Button>
                    )}
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      <ProjectModal editing={editing} onClose={() => setEditing(null)} />
    </Stack>
  );
}
