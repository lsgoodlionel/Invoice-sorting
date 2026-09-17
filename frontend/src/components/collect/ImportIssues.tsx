import { Alert, List, Text } from '@mantine/core';
import type { ImportDuplicate, ImportError, ImportNotice } from '../../api/types';

interface ImportIssuesProps {
  duplicates: readonly ImportDuplicate[];
  errors: readonly ImportError[];
  notices: readonly ImportNotice[];
}

export function ImportIssues({ duplicates, errors, notices }: ImportIssuesProps) {
  return (
    <>
      {duplicates.length > 0 && (
        <Alert color="yellow" variant="light" title={`${duplicates.length} 个重复文件已跳过`}>
          <List size="sm" spacing={2}>
            {duplicates.map((item) => (
              <List.Item key={item.original_name}>
                {item.original_name}
                <Text span size="xs" c="dimmed">
                  　{item.reason}
                  {item.existing_expense_id !== null && `（已在支出 #${item.existing_expense_id}）`}
                </Text>
              </List.Item>
            ))}
          </List>
        </Alert>
      )}
      {notices.length > 0 && (
        <Alert color="yellow" variant="light" title={`${notices.length} 个文件需要留意`}>
          <List size="sm" spacing={2}>
            {notices.map((item) => (
              <List.Item key={item.original_name}>
                {item.original_name}<Text span size="xs" c="dimmed">　{item.message}</Text>
              </List.Item>
            ))}
          </List>
        </Alert>
      )}
      {errors.length > 0 && (
        <Alert color="red" variant="light" title={`${errors.length} 个文件导入失败`}>
          <List size="sm" spacing={2}>
            {errors.map((item) => (
              <List.Item key={item.original_name}>
                {item.original_name}<Text span size="xs" c="dimmed">　{item.error}</Text>
              </List.Item>
            ))}
          </List>
        </Alert>
      )}
    </>
  );
}
