import { Select, Text, type ComboboxItem, type SelectProps } from '@mantine/core';
import { useState } from 'react';
import { useProjects } from '../api/hooks/settings';
import type { Project } from '../api/types';
import { ProjectCreateModal } from './ProjectCreateModal';

interface ProjectSelectProps extends Omit<SelectProps, 'data' | 'value' | 'onChange'> {
  value: number | null;
  onChange: (id: number | null) => void;
  /** 下拉底部是否提供“新建经费项目”入口（筛选场景传 false） */
  creatable?: boolean;
}

/** 下拉中固定位于底部的“新建”伪选项，选中时打开新建弹窗而不改变当前值。 */
const CREATE_VALUE = '__create_project__';
const CREATE_LABEL = '＋ 新建经费项目';

function projectLabel(project: Project): string {
  return project.code ? `${project.code} ${project.name}` : project.name;
}

function renderOption({ option }: { option: ComboboxItem }) {
  if (option.value !== CREATE_VALUE) return option.label;
  return <Text size="sm" fw={600} c="ink">{option.label}</Text>;
}

export function ProjectSelect({ value, onChange, creatable = true, ...rest }: ProjectSelectProps) {
  const { data = [] } = useProjects();
  const [isCreateOpen, setCreateOpen] = useState(false);
  const options = data
    .filter((project) => project.active || project.id === value)
    .map((project) => ({ value: String(project.id), label: projectLabel(project) }));
  const items = creatable ? [...options, { value: CREATE_VALUE, label: CREATE_LABEL }] : options;

  const handleChange = (next: string | null) => {
    if (next === CREATE_VALUE) return setCreateOpen(true);
    onChange(next === null ? null : Number(next));
  };

  return (
    <>
      <Select
        placeholder={creatable ? '选择经费项目（可新建）' : '经费项目'}
        nothingFoundMessage="还没有经费项目"
        data={items}
        renderOption={renderOption}
        value={value === null ? null : String(value)}
        onChange={handleChange}
        {...rest}
      />
      {creatable && (
        <ProjectCreateModal
          opened={isCreateOpen}
          onClose={() => setCreateOpen(false)}
          onCreated={(project) => onChange(project.id)}
        />
      )}
    </>
  );
}
