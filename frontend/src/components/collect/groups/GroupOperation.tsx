import { Select, Stack } from '@mantine/core';
import { operationOptions, operationValue, parseOperationValue, type GroupDraft, type OperationChoice } from '../../../lib/importGroups';
import { ExpenseSelect } from '../../ExpenseSelect';

interface GroupOperationProps {
  group: GroupDraft;
  onChange: (operation: OperationChoice) => void;
}

const DROPDOWN_WIDTH = 420;

/** 操作：新建 / 挂到匹配或候选 / 搜索其他记录 / 留在待归属。 */
export function GroupOperation({ group, onChange }: GroupOperationProps) {
  const { operation } = group;
  return (
    <Stack gap={4}>
      <Select
        size="xs"
        label="操作"
        aria-label="操作"
        data={operationOptions(group)}
        value={operationValue(operation)}
        allowDeselect={false}
        comboboxProps={{ width: DROPDOWN_WIDTH, position: 'bottom-end' }}
        onChange={(value) => {
          const next = value ? parseOperationValue(value) : null;
          if (next) onChange(next);
        }}
      />
      {operation.type === 'search' && (
        <ExpenseSelect
          size="xs"
          aria-label="搜索记录"
          value={operation.expenseId}
          error={operation.expenseId === null}
          comboboxProps={{ width: DROPDOWN_WIDTH, position: 'bottom-end' }}
          onChange={(expenseId) => onChange({ type: 'search', expenseId })}
        />
      )}
    </Stack>
  );
}
