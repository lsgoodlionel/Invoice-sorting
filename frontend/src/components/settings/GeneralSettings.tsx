import { Button, Group, NumberInput, SimpleGrid, Stack, Text, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useEffect, useState } from 'react';
import { useBackup, useSettings, useUpdateSettings } from '../../api/hooks/settings';
import type { Settings, SettingsPatch } from '../../api/types';
import { DEFAULT_LOCAL_REGION } from '../../lib/region';
import { RegionSettingsFields } from './RegionSettingsFields';

const MIN_OVERDUE_DAYS = 1;
const MAX_OVERDUE_DAYS = 365;

interface SettingsForm {
  buyerName: string;
  buyerTaxId: string;
  overdueDays: number;
  localRegion: string;
  detailPlatforms: string[];
}

const EMPTY_FORM: SettingsForm = { buyerName: '', buyerTaxId: '', overdueDays: 30, localRegion: DEFAULT_LOCAL_REGION, detailPlatforms: [] };

function formFrom(data: Settings): SettingsForm {
  return {
    buyerName: data.buyer_name,
    buyerTaxId: data.buyer_tax_id,
    overdueDays: data.overdue_days,
    localRegion: data.local_region || DEFAULT_LOCAL_REGION,
    detailPlatforms: data.detail_platforms ?? [],
  };
}

function uniqueTrimmed(values: readonly string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}

function toPayload(form: SettingsForm): SettingsPatch {
  return {
    buyer_name: form.buyerName.trim(),
    buyer_tax_id: form.buyerTaxId.trim(),
    overdue_days: form.overdueDays,
    local_region: form.localRegion,
    detail_platforms: uniqueTrimmed(form.detailPlatforms),
  };
}

function BackupButton() {
  const backup = useBackup();
  return (
    <Button
      variant="outline"
      loading={backup.isPending}
      onClick={() => backup.mutate(undefined, { onSuccess: (r) => notifications.show({ color: 'ink', title: '备份完成', message: r.file }) })}
    >
      立即备份
    </Button>
  );
}

/** readOnly：非管理员只读（输入框禁用，隐藏保存与备份）。 */
export function GeneralSettings({ readOnly = false }: { readOnly?: boolean }) {
  const { data } = useSettings();
  const update = useUpdateSettings();
  const [form, setForm] = useState<SettingsForm>(EMPTY_FORM);
  const patch = (p: Partial<SettingsForm>) => setForm((current) => ({ ...current, ...p }));

  useEffect(() => {
    if (data) setForm(formFrom(data));
  }, [data]);

  const save = () =>
    update.mutate(toPayload(form), { onSuccess: () => notifications.show({ color: 'ink', message: '设置已保存' }) });

  return (
    <fieldset disabled={readOnly} className="plain-fieldset">
      <Stack gap="sm">
        <SimpleGrid cols={{ base: 1, md: 3 }} spacing="sm">
          <TextInput label="购方抬头" description="用于校验发票购买方名称" value={form.buyerName} onChange={(e) => patch({ buyerName: e.currentTarget.value })} />
          <TextInput label="购方税号" value={form.buyerTaxId} classNames={{ input: 'num' }} onChange={(e) => patch({ buyerTaxId: e.currentTarget.value })} />
          <NumberInput
            label="超期提醒天数"
            description="已外发超过该天数未到账时提醒"
            min={MIN_OVERDUE_DAYS}
            max={MAX_OVERDUE_DAYS}
            allowDecimal={false}
            value={form.overdueDays}
            onChange={(value) => typeof value === 'number' && patch({ overdueDays: value })}
          />
        </SimpleGrid>
        <RegionSettingsFields localRegion={form.localRegion} detailPlatforms={form.detailPlatforms} onChange={patch} />
        <Group justify="space-between" align="flex-end">
          <Stack gap={2} className="settings-paths">
            <Text size="xs" c="dimmed">数据目录：<span className="path-text">{data?.data_dir ?? '—'}</span></Text>
            <Text size="xs" c="dimmed">收件箱：<span className="path-text">{data?.inbox_dir ?? '—'}</span>（可把发票直接放进该文件夹，程序会自动导入）</Text>
          </Stack>
          {!readOnly && (
            <Group gap="xs">
              <BackupButton />
              <Button variant="filled" onClick={save} loading={update.isPending}>保存设置</Button>
            </Group>
          )}
        </Group>
      </Stack>
    </fieldset>
  );
}
