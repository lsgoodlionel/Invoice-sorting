import { Button, Group, NumberInput, SimpleGrid, Stack, Text, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useEffect, useState } from 'react';
import { useBackup, useSettings, useUpdateSettings } from '../../api/hooks/settings';

const MIN_OVERDUE_DAYS = 1;
const MAX_OVERDUE_DAYS = 365;

export function GeneralSettings() {
  const { data } = useSettings();
  const update = useUpdateSettings();
  const backup = useBackup();
  const [form, setForm] = useState({ buyerName: '', buyerTaxId: '', overdueDays: 30 });

  useEffect(() => {
    if (data) setForm({ buyerName: data.buyer_name, buyerTaxId: data.buyer_tax_id, overdueDays: data.overdue_days });
  }, [data]);

  const save = () =>
    update.mutate(
      { buyer_name: form.buyerName.trim(), buyer_tax_id: form.buyerTaxId.trim(), overdue_days: form.overdueDays },
      { onSuccess: () => notifications.show({ color: 'ink', message: '设置已保存' }) },
    );

  return (
    <Stack gap="sm">
      <SimpleGrid cols={{ base: 1, md: 3 }} spacing="sm">
        <TextInput label="购方抬头" description="用于校验发票购买方名称" value={form.buyerName} onChange={(e) => { const buyerName = e.currentTarget.value; setForm((f) => ({ ...f, buyerName })); }} />
        <TextInput label="购方税号" value={form.buyerTaxId} classNames={{ input: 'num' }} onChange={(e) => { const buyerTaxId = e.currentTarget.value; setForm((f) => ({ ...f, buyerTaxId })); }} />
        <NumberInput
          label="超期提醒天数"
          description="已外发超过该天数未到账时提醒"
          min={MIN_OVERDUE_DAYS}
          max={MAX_OVERDUE_DAYS}
          allowDecimal={false}
          value={form.overdueDays}
          onChange={(value) => typeof value === 'number' && setForm((f) => ({ ...f, overdueDays: value }))}
        />
      </SimpleGrid>
      <Group justify="space-between" align="flex-end">
        <Stack gap={2}>
          <Text size="xs" c="dimmed">数据目录：<span className="num">{data?.data_dir ?? '—'}</span></Text>
          <Text size="xs" c="dimmed">收件箱：<span className="num">{data?.inbox_dir ?? '—'}</span>（可把发票直接放进该文件夹，程序会自动导入）</Text>
        </Stack>
        <Group gap="xs">
          <Button
            variant="outline"
            loading={backup.isPending}
            onClick={() => backup.mutate(undefined, { onSuccess: (r) => notifications.show({ color: 'ink', title: '备份完成', message: r.file }) })}
          >
            立即备份
          </Button>
          <Button variant="filled" onClick={save} loading={update.isPending}>保存设置</Button>
        </Group>
      </Group>
    </Stack>
  );
}
