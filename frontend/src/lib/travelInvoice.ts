// 差旅发票分类（住宿 / 交通票 / 其他）、组内多发票校验与金额构成。
import type { Attachment, InvoiceData } from '../api/types';
import { formatCents } from './money';

export type InvoiceClass = 'lodging' | 'transport' | 'other';

/** 多发票组的问题：lodging=多张住宿发票；multiple=除一张住宿发票外还有非交通票发票（或没有住宿发票）。 */
export type InvoiceMixProblem = 'lodging' | 'multiple';

const TRANSPORT_KEYWORDS = ['旅客运输', '客运', '铁路', '航空', '机票', '船票', '汽车票'];
const LODGING_KEYWORDS = ['住宿', '酒店', '宾馆', '旅馆', '民宿', '客栈'];

function containsAny(text: string, keywords: readonly string[]): boolean {
  return keywords.some((keyword) => text.includes(keyword));
}

/** 交通票发票：details.vehicle 非空，或税收分类/商品/票种含旅客运输等关键词。 */
export function isTransportInvoice(invoice: InvoiceData): boolean {
  if ((invoice.details?.vehicle ?? '').trim()) return true;
  return containsAny(`${invoice.tax_category} ${invoice.item_summary} ${invoice.invoice_type}`, TRANSPORT_KEYWORDS);
}

/** 住宿发票：税收分类/商品/销售方含住宿、酒店、宾馆等。 */
export function isLodgingInvoice(invoice: InvoiceData): boolean {
  return containsAny(`${invoice.tax_category} ${invoice.item_summary} ${invoice.seller_name}`, LODGING_KEYWORDS);
}

export function classifyInvoice(invoice: InvoiceData | null): InvoiceClass {
  if (!invoice) return 'other';
  if (isTransportInvoice(invoice)) return 'transport';
  return isLodgingInvoice(invoice) ? 'lodging' : 'other';
}

/** 一组内允许：至多一张发票，或一张住宿发票 + 若干交通票发票。 */
export function invoiceMixProblem(invoices: readonly (InvoiceData | null)[]): InvoiceMixProblem | null {
  if (invoices.length <= 1) return null;
  const classes = invoices.map(classifyInvoice);
  const lodgingCount = classes.filter((item) => item === 'lodging').length;
  if (lodgingCount > 1) return 'lodging';
  const isLodgingWithTransport = lodgingCount === 1 && classes.every((item) => item !== 'other');
  return isLodgingWithTransport ? null : 'multiple';
}

function invoicesOf(attachments: readonly Attachment[]): InvoiceData[] {
  return attachments.filter((item) => item.kind === 'invoice').flatMap((item) => (item.invoice ? [item.invoice] : []));
}

function sumTotals(invoices: readonly InvoiceData[]): number {
  return invoices.reduce((sum, invoice) => sum + (invoice.total_cents ?? 0), 0);
}

/** 类型为发票的附件价税合计之和；没有可用金额时为 null。 */
export function invoicesTotalCents(attachments: readonly Attachment[]): number | null {
  const withTotal = invoicesOf(attachments).filter((invoice) => invoice.total_cents !== null);
  return withTotal.length ? sumTotals(withTotal) : null;
}

export interface AmountCompositionInfo {
  /** "¥1,025.00 = 住宿 ¥720.00 + 交通 2 张 ¥305.00" */
  text: string;
  invoiceTotalCents: number;
  isMismatch: boolean;
}

function bucketText(label: string, invoices: readonly InvoiceData[], alwaysCount: boolean): string {
  if (invoices.length === 0) return '';
  const count = alwaysCount || invoices.length > 1 ? ` ${invoices.length} 张` : '';
  return `${label}${count} ${formatCents(sumTotals(invoices))}`;
}

/** 含交通票发票的记录金额构成；没有交通票发票时为 null。 */
export function amountComposition(amountCents: number, attachments: readonly Attachment[]): AmountCompositionInfo | null {
  const invoices = invoicesOf(attachments);
  const byClass = (target: InvoiceClass) => invoices.filter((invoice) => classifyInvoice(invoice) === target);
  const transport = byClass('transport');
  if (transport.length === 0) return null;
  const parts = [bucketText('住宿', byClass('lodging'), false), bucketText('交通', transport, true), bucketText('其他', byClass('other'), false)];
  const invoiceTotalCents = sumTotals(invoices);
  return {
    text: `${formatCents(amountCents)} = ${parts.filter(Boolean).join(' + ')}`,
    invoiceTotalCents,
    isMismatch: invoiceTotalCents !== amountCents,
  };
}
