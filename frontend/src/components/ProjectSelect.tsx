import { Select, type SelectProps } from '@mantine/core';
import { useProjects } from '../api/hooks/settings';

interface ProjectSelectProps extends Omit<SelectProps, 'data' | 'value' | 'onChange'> {
  value: number | null;
  onChange: (id: number | null) => void;
}

export function ProjectSelect({ value, onChange, ...rest }: ProjectSelectProps) {
  const { data = [] } = useProjects();
  const options = data
    .filter((project) => project.active || project.id === value)
    .map((project) => ({
      value: String(project.id),
      label: project.code ? `${project.code} ${project.name}` : project.name,
    }));
  return (
    <Select
      placeholder="经费项目"
      data={options}
      value={value === null ? null : String(value)}
      onChange={(next) => onChange(next === null ? null : Number(next))}
      {...rest}
    />
  );
}
