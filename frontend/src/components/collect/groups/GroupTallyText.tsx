import { Group, Text } from '@mantine/core';
import type { GroupTally } from '../../../lib/importGroups';
import { HelpLabel } from '../../HelpLabel';

export const MATCH_HELP =
  '系统会把同一笔支出的发票、订单、支付记录归为一组（依据：订单号、文件名、金额与日期）；如果之前已有记录缺少这些凭证，会建议挂到那条记录上。';

export function GroupTallyText({ tally }: { tally: GroupTally }) {
  return (
    <Group gap="sm" wrap="wrap">
      <Text size="sm" data-testid="import-tally">
        共 <b className="num">{tally.total}</b> 组 · 新建 <b className="num">{tally.create}</b> · 挂到已有 <b className="num">{tally.attach}</b> · 留待归属 <b className="num">{tally.skip}</b>
      </Text>
      <Text size="xs" c="dimmed" component="span"><HelpLabel label="分组与匹配" help={MATCH_HELP} /></Text>
    </Group>
  );
}
