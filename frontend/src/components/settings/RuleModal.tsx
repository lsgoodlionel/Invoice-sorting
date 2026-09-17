import { Button, Checkbox, Group, Modal, SegmentedControl, Select, SimpleGrid, Stack, Switch, TagsInput, Text, Textarea } from '@mantine/core';
import { useEffect, useState } from 'react';
import { useCategories, useSaveRule } from '../../api/hooks/settings';
import type { AttachmentKind, ChecklistLevel, ChecklistRule } from '../../api/types';
import { buildCondition, conditionSwitches, INVOICE_EXEMPT_OPTIONS, type ConditionSwitches, type InvoiceExemptFilter } from '../../lib/rules';
import { ATTACHMENT_KIND_OPTIONS } from '../../lib/status';
import { MoneyInput } from '../MoneyInput';

interface RuleDraft extends ConditionSwitches {
  categoryId: string;
  kind: AttachmentKind;
  level: ChecklistLevel;
  amountGte: number | null;
  amountLt: number | null;
  hint: string;
}

const GENERAL = 'general';

function draftFrom(rule: ChecklistRule | null): RuleDraft {
  return {
    categoryId: rule?.category_id === null || !rule ? GENERAL : String(rule.category_id),
    kind: rule?.attachment_kind ?? 'invoice',
    level: rule?.level ?? 'required',
    amountGte: rule?.condition.amount_gte ?? null,
    amountLt: rule?.condition.amount_lt ?? null,
    ...conditionSwitches(rule?.condition ?? {}),
    hint: rule?.hint ?? '',
  };
}

export function RuleModal({ editing, onClose }: { editing: ChecklistRule | 'new' | null; onClose: () => void }) {
  const { data: categories = [] } = useCategories();
  const save = useSaveRule();
  const [draft, setDraft] = useState<RuleDraft>(() => draftFrom(null));
  useEffect(() => {
    if (editing !== null) setDraft(draftFrom(editing === 'new' ? null : editing));
  }, [editing]);
  const patch = (p: Partial<RuleDraft>) => setDraft((current) => ({ ...current, ...p }));

  const submit = () =>
    save.mutate(
      {
        id: editing === 'new' || !editing ? null : editing.id,
        input: {
          category_id: draft.categoryId === GENERAL ? null : Number(draft.categoryId),
          attachment_kind: draft.kind,
          level: draft.level,
          condition: buildCondition(draft),
          hint: draft.hint.trim(),
        },
      },
      { onSuccess: onClose },
    );

  const categoryOptions = [{ value: GENERAL, label: '通用（所有分类）' }, ...categories.filter((c) => !c.archived).map((c) => ({ value: String(c.id), label: c.name }))];

  return (
    <Modal opened={editing !== null} onClose={onClose} title={editing === 'new' ? '新增凭证规则' : '编辑凭证规则'} size="lg">
      <Stack gap="sm">
        <SimpleGrid cols={2} spacing="sm">
          <Select label="适用分类" data={categoryOptions} value={draft.categoryId} allowDeselect={false} onChange={(v) => v && patch({ categoryId: v })} />
          <Select label="附件类型" data={ATTACHMENT_KIND_OPTIONS} value={draft.kind} allowDeselect={false} onChange={(v) => v && patch({ kind: v as AttachmentKind })} />
        </SimpleGrid>
        <SegmentedControl
          data={[{ value: 'required', label: '必需' }, { value: 'suggested', label: '建议' }]}
          value={draft.level}
          onChange={(v) => patch({ level: v === 'suggested' ? 'suggested' : 'required' })}
        />
        <SimpleGrid cols={3} spacing="sm">
          <MoneyInput label="金额 ≥（元）" cents={draft.amountGte} onCentsChange={(amountGte) => patch({ amountGte })} />
          <MoneyInput label="金额 <（元）" cents={draft.amountLt} onCentsChange={(amountLt) => patch({ amountLt })} />
          <Checkbox mt={30} label="仅网购" checked={draft.isOnlineOnly} onChange={(e) => patch({ isOnlineOnly: e.currentTarget.checked })} />
        </SimpleGrid>
        <Group gap="lg">
          <Switch label="仅外地发票" checked={draft.isNonlocalOnly} onChange={(e) => patch({ isNonlocalOnly: e.currentTarget.checked })} />
          <Switch label="排除已带明细平台" checked={draft.excludeDetailPlatform} onChange={(e) => patch({ excludeDetailPlatform: e.currentTarget.checked })} />
        </Group>
        <Select
          label="免发票记录"
          aria-label="免发票记录"
          w={220}
          data={INVOICE_EXEMPT_OPTIONS}
          value={draft.invoiceExempt}
          allowDeselect={false}
          onChange={(v) => v && patch({ invoiceExempt: v as InvoiceExemptFilter })}
        />
        <SimpleGrid cols={2} spacing="sm">
          <TagsInput
            label="发票内容含（任一）"
            placeholder="如 住宿、酒店，回车添加"
            value={draft.contentKeywords}
            onChange={(contentKeywords) => patch({ contentKeywords })}
          />
          <TagsInput
            label="发票内容不含（任一）"
            placeholder="回车添加"
            value={draft.excludeKeywords}
            onChange={(excludeKeywords) => patch({ excludeKeywords })}
          />
        </SimpleGrid>
        <Text size="xs" c="dimmed">发票内容：发票的税收分类、商品名称、销售方，以及记录的商家与摘要。外地：开票地区不等于设置中的本地地区；已带明细平台见“通用设置”；免发票记录：境外消费等无法取得发票的记录。</Text>
        <Textarea label="提示文字" autosize minRows={2} value={draft.hint} onChange={(e) => patch({ hint: e.currentTarget.value })} />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>取消</Button>
          <Button variant="filled" loading={save.isPending} onClick={submit}>保存</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
