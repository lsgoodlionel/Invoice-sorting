import { Badge, Checkbox, Group, Table, Text } from '@mantine/core';
import type { ExpenseSummary } from '../../api/types';
import type { ExpenseColumnKey } from '../../lib/expenseColumns';
import { formatCents, formatMoney, isForeignCurrency } from '../../lib/money';
import { CategoryDot } from '../CategoryDot';
import { StatusBadge } from '../StatusBadge';
import { useFileDropTarget } from './useFileDropTarget';

interface ExpenseRowProps {
  expense: ExpenseSummary;
  isSelected: boolean;
  onToggle: (id: number) => void;
  onOpen: (id: number) => void;
  onDropFiles: (id: number, files: File[]) => void;
  columns: readonly ExpenseColumnKey[];
}

const MERCHANT_MAX_WIDTH = 320;

function MerchantBadges({ expense }: { expense: ExpenseSummary }) {
  return (
    <>
      {expense.is_nonlocal && (
        <Badge size="xs" radius="xs" color="orange" variant="light" title={`开票地区：${expense.region_name}`} style={{ flexShrink: 0 }}>外地</Badge>
      )}
      {expense.invoice_exempt && (
        <Badge size="xs" radius="xs" color="grape" variant="light" title="境外消费等无法取得发票" style={{ flexShrink: 0 }}>免发票</Badge>
      )}
      {expense.travel_scope && (
        <Badge
          size="xs"
          radius="xs"
          color={expense.travel_scope === 'local' ? 'blue' : 'teal'}
          variant="light"
          title={expense.travel_scope_manual ? '手工设置' : '根据本地地区和行程自动识别'}
          style={{ flexShrink: 0 }}
        >
          {expense.travel_scope_label}
        </Badge>
      )}
      {expense.travel_dates_missing && (
        <Badge size="xs" radius="xs" color="orange" variant="outline" title="补充酒店订单或支付水单后可自动关联往返交通">
          待补住宿时间
        </Badge>
      )}
    </>
  );
}

function AmountCell({ expense }: { expense: ExpenseSummary }) {
  const hasOriginal = isForeignCurrency(expense.currency) && expense.original_amount_cents !== null;
  return (
    <Table.Td ta="right" className="num" fw={500}>
      {formatCents(expense.amount_cents)}
      {hasOriginal && (
        <Text size="xs" c="dimmed" fw={400} className="num">{formatMoney(expense.original_amount_cents, expense.currency)}</Text>
      )}
    </Table.Td>
  );
}

/** 摘要行：摘要 + 宽屏时小字“创建：张三”（不占额外列宽）。 */
function SummaryLine({ expense }: { expense: ExpenseSummary }) {
  if (!expense.summary && !expense.created_by) return null;
  return (
    <Group gap={8} wrap="nowrap">
      {expense.summary && <Text size="xs" c="dimmed" truncate style={{ minWidth: 0 }}>{expense.summary}</Text>}
      {expense.created_by && (
        <Text size="xs" c="dimmed" visibleFrom="md" className="expense-creator" truncate>创建：{expense.created_by.display_name}</Text>
      )}
    </Group>
  );
}

/** 清单行：点击打开详情；拖入文件即上传到该记录。 */
export function ExpenseRow({ expense, isSelected, onToggle, onOpen, onDropFiles, columns }: ExpenseRowProps) {
  const { isOver, handlers } = useFileDropTarget((files) => onDropFiles(expense.id, files));
  return (
    <Table.Tr
      className="clickable"
      tabIndex={0}
      data-selected={isSelected}
      data-drop-over={isOver || undefined}
      data-testid={`expense-row-${expense.id}`}
      onClick={() => onOpen(expense.id)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') onOpen(expense.id);
      }}
      {...handlers}
    >
      <Table.Td onClick={(event) => event.stopPropagation()} w={36}>
        <Checkbox size="xs" aria-label={`选择 ${expense.merchant}`} checked={isSelected} onChange={() => onToggle(expense.id)} />
      </Table.Td>
      {columns.includes('spent_on') && <Table.Td className="num" w={110}>{expense.spent_on}</Table.Td>}
      {columns.includes('issued_on') && <Table.Td className="num" w={110}>{expense.issued_on ?? '—'}</Table.Td>}
      {columns.includes('created_on') && <Table.Td className="num" w={110}>{expense.created_on ?? '—'}</Table.Td>}
      {columns.includes('summary') && <Table.Td style={{ maxWidth: MERCHANT_MAX_WIDTH }}>
        <Group gap={6} wrap="nowrap">
          <Text size="sm" fw={500} truncate>{expense.merchant}</Text>
          <MerchantBadges expense={expense} />
        </Group>
        {isOver ? (
          <Text size="xs" className="drop-hint">松开上传到此记录</Text>
        ) : (
          <SummaryLine expense={expense} />
        )}
      </Table.Td>}
      {columns.includes('item_name') && <Table.Td><Text size="sm" truncate maw={220}>{expense.item_name ?? expense.summary}</Text></Table.Td>}
      {columns.includes('category') && <Table.Td><CategoryDot color={expense.category_color} name={expense.category_name} /></Table.Td>}
      {columns.includes('lab_platform') && <Table.Td><Badge size="xs" color={expense.requires_lab_platform ? 'orange' : 'gray'} variant="light">{expense.requires_lab_platform === null ? '未判定' : expense.requires_lab_platform ? '需要' : '无需'}</Badge></Table.Td>}
      {columns.includes('unit_price') && <Table.Td ta="right" className="num">{expense.unit_price_cents === null ? '—' : formatCents(expense.unit_price_cents)}</Table.Td>}
      {columns.includes('quantity') && <Table.Td ta="right" className="num">{expense.quantity ?? '—'}</Table.Td>}
      {columns.includes('amount') && <AmountCell expense={expense} />}
      {columns.includes('invoice_no') && <Table.Td><Text size="xs" className="num" truncate maw={180}>{expense.invoice_no ?? '—'}</Text></Table.Td>}
      {columns.includes('status') && <Table.Td><StatusBadge status={expense.status} manual={expense.status_manual} /></Table.Td>}
      {columns.includes('evidence') && <Table.Td>
        {expense.missing_count > 0 && <Badge size="sm" color="orange" variant="outline">缺 {expense.missing_count} 项</Badge>}
      </Table.Td>}
      {columns.includes('batch') && <Table.Td><Text size="xs" c="dimmed" truncate maw={160}>{expense.batch_name ?? ''}</Text></Table.Td>}
    </Table.Tr>
  );
}
