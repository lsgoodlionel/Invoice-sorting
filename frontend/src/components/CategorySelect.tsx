import { Select, type SelectProps } from '@mantine/core';
import { useCategories } from '../api/hooks/settings';

interface CategorySelectProps extends Omit<SelectProps, 'data' | 'value' | 'onChange'> {
  value: number | null;
  onChange: (id: number | null) => void;
  includeArchived?: boolean;
}

export function CategorySelect({ value, onChange, includeArchived = false, ...rest }: CategorySelectProps) {
  const { data = [] } = useCategories();
  const options = data
    .filter((category) => includeArchived || !category.archived || category.id === value)
    .map((category) => ({ value: String(category.id), label: category.name }));
  return (
    <Select
      placeholder="分类"
      data={options}
      value={value === null ? null : String(value)}
      onChange={(next) => onChange(next === null ? null : Number(next))}
      {...rest}
    />
  );
}
