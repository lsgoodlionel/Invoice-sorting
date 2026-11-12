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
  documentTotalCents: number;
  isMismatch: boolean;
}

interface AmountEntry {
  key: string;
  cents: number;
  invoice: boolean;
}

function travelKey(attachment: Attachment): string {
  const details = attachment.invoice?.details ?? attachment.evidence?.details ?? {};
  const route = [details.date, details.vehicle, details.number, details.from, details.to].map((item) => item ?? '').join('|');
  return route.replaceAll('|', '') ? route : `attachment:${attachment.id}`;
}

function isTransportEvidence(attachment: Attachment): boolean {
  const evidence = attachment.evidence;
  if (!evidence) return false;
  return attachment.kind === 'transport'
    || evidence.recognizer === 'transport_booking'
    || evidence.recognizer === 'ride_itinerary'
    || Boolean(evidence.details?.vehicle);
}

function transportEntries(attachments: readonly Attachment[]): AmountEntry[] {
  const grouped = new Map<string, AmountEntry>();
  attachments.forEach((attachment) => {
    const invoice = attachment.kind === 'invoice' && classifyInvoice(attachment.invoice) === 'transport';
    const evidence = isTransportEvidence(attachment);
    const cents = invoice ? attachment.invoice?.total_cents : attachment.evidence?.cny_cents;
    if ((!invoice && !evidence) || cents === null || cents === undefined) return;
    const key = travelKey(attachment);
    const current = grouped.get(key);
    if (!current || (invoice && !current.invoice)) grouped.set(key, { key, cents, invoice });
  });
  return [...grouped.values()];
}

function lodgingTotal(attachments: readonly Attachment[], invoices: readonly InvoiceData[]): number {
  const lodgingInvoices = invoices.filter((invoice) => classifyInvoice(invoice) === 'lodging');
  if (lodgingInvoices.length) return sumTotals(lodgingInvoices);
  const order = attachments.find((item) => item.evidence?.recognizer === 'hotel_booking' && item.evidence.cny_cents !== null);
  return order?.evidence?.cny_cents ?? 0;
}

function part(label: string, count: number, cents: number, alwaysCount = false): string {
  if (count === 0) return '';
  const countText = alwaysCount || count > 1 ? ` ${count} 张` : '';
  return `${label}${countText} ${formatCents(cents)}`;
}

/** 住宿服务与交通凭证的累计净额；同一行程的发票和订单/行程单只计一次。 */
export function amountComposition(amountCents: number, attachments: readonly Attachment[]): AmountCompositionInfo | null {
  const invoices = invoicesOf(attachments);
  const transport = transportEntries(attachments);
  if (transport.length === 0) return null;
  const lodgingInvoices = invoices.filter((invoice) => classifyInvoice(invoice) === 'lodging');
  const other = invoices.filter((invoice) => classifyInvoice(invoice) === 'other');
  const lodgingCents = lodgingTotal(attachments, invoices);
  const transportCents = transport.reduce((sum, entry) => sum + entry.cents, 0);
  const otherCents = sumTotals(other);
  const parts = [
    part('住宿', lodgingCents > 0 ? Math.max(lodgingInvoices.length, 1) : 0, lodgingCents),
    part('交通', transport.length, transportCents, true),
    part('其他', other.length, otherCents),
  ];
  const documentTotalCents = lodgingCents + transportCents + otherCents;
  return {
    text: `${formatCents(amountCents)} = ${parts.filter(Boolean).join(' + ')}`,
    documentTotalCents,
    isMismatch: documentTotalCents !== amountCents,
  };
}
