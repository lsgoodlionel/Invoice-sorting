// 非发票凭证识别结果的摘要文案，以及附件识别要点。
import type { Attachment, EvidenceData, EvidenceDocType, ExpenseDetail } from '../api/types';
import { formatCents, formatMoney, isForeignCurrency } from './money';

export const EVIDENCE_TYPE_LABELS: Readonly<Record<EvidenceDocType, string>> = {
  order: '订单',
  receipt: '收据',
  payment: '银行交易',
  itinerary: '行程单',
  unknown: '未识别',
};

export const UNRECOGNIZED_TEXT = '未识别（可在下方手动归属）';

const ORDER_TAIL_LENGTH = 6;

export function isEvidenceRecognized(evidence: EvidenceData | null): evidence is EvidenceData {
  return evidence !== null && evidence.doc_type !== 'unknown';
}

function orderNoText(orderNo: string, useTail: boolean): string {
  if (!orderNo) return '';
  const shown = useTail && orderNo.length > ORDER_TAIL_LENGTH ? `…${orderNo.slice(-ORDER_TAIL_LENGTH)}` : orderNo;
  return `订单号 ${shown}`;
}

/** 类型 · 日期 · 金额（按币种）· 商户/商品 · 订单号；空字段省略。 */
export function evidenceParts(evidence: EvidenceData, options: { orderNoTail?: boolean } = {}): string[] {
  const amount = evidence.amount_cents === null ? '' : formatMoney(evidence.amount_cents, evidence.currency);
  const party = [evidence.merchant, evidence.item_name].filter(Boolean).join(' / ');
  return [
    EVIDENCE_TYPE_LABELS[evidence.doc_type],
    evidence.occurred_on ?? '',
    amount,
    party,
    orderNoText(evidence.order_no, options.orderNoTail ?? false),
  ].filter(Boolean);
}

export interface AttachmentFact {
  label: string;
  value: string;
}

function evidenceAmount(evidence: EvidenceData): string {
  if (evidence.amount_cents === null) return '—';
  const base = formatMoney(evidence.amount_cents, evidence.currency);
  const hasCny = isForeignCurrency(evidence.currency) && evidence.cny_cents !== null;
  return hasCny ? `${base}（${formatCents(evidence.cny_cents)}）` : base;
}

/** 文件卡片 tooltip：发票号 / 订单号 / 金额币种 / 日期。 */
export function attachmentFacts(attachment: Attachment): AttachmentFact[] {
  const { invoice, evidence } = attachment;
  if (invoice) {
    return [
      { label: '发票号', value: invoice.invoice_no || '—' },
      { label: '订单号', value: invoice.order_no || '—' },
      { label: '金额', value: formatCents(invoice.total_cents) },
      { label: '日期', value: invoice.issued_on ?? '—' },
    ];
  }
  if (!evidence) return [];
  return [
    { label: '订单号', value: evidence.order_no || '—' },
    { label: '金额', value: evidenceAmount(evidence) },
    { label: '日期', value: evidence.occurred_on ?? '—' },
  ];
}

/** 清单行拖放上传成功提示：取 id 最大的 N 个附件的类型。 */
export function uploadResultMessage(detail: Pick<ExpenseDetail, 'id' | 'attachments'>, fileCount: number): string {
  const base = `已上传 ${fileCount} 个文件到 #${detail.id}`;
  const newest = [...detail.attachments].sort((a, b) => a.id - b.id).slice(-fileCount);
  const labels = [...new Set(newest.map((item) => item.kind_label))];
  return labels.length ? `${base}，识别为：${labels.join('、')}` : base;
}
