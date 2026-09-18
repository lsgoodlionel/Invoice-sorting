// 差旅凭证结构化信息（details）的摘要文案：酒店订单、往来交通凭证、交通票发票。
import type { Attachment, EvidenceData } from '../api/types';
import { formatMoney } from './money';

type Details = Readonly<Record<string, string>> | null | undefined;

export const VEHICLE_LABELS: Readonly<Record<string, string>> = {
  train: '火车',
  flight: '飞机',
  bus: '汽车',
  ship: '轮船',
};

const UNKNOWN_VEHICLE_LABEL = '交通';
const UNKNOWN_PLACE = '？';
const ORDER_TAIL_LENGTH = 6;
const ISO_DATE_PATTERN = /^\d{4}-(\d{2}-\d{2})/;

function field(details: Details, key: string): string {
  return (details?.[key] ?? '').trim();
}

/** "2026-08-15" → "08-15"；非 ISO 日期原样返回。 */
export function shortDate(value: string | null | undefined): string {
  const text = (value ?? '').trim();
  return ISO_DATE_PATTERN.exec(text)?.[1] ?? text;
}

/** "订单号 1132…"；useTail 时只显示末 6 位。 */
export function orderNoText(orderNo: string, useTail: boolean): string {
  if (!orderNo) return '';
  const shown = useTail && orderNo.length > ORDER_TAIL_LENGTH ? `…${orderNo.slice(-ORDER_TAIL_LENGTH)}` : orderNo;
  return `订单号 ${shown}`;
}

export function hasHotelDetails(details: Details): boolean {
  return Boolean(field(details, 'hotel') || field(details, 'check_in'));
}

export function hasTransportDetails(details: Details): boolean {
  return Boolean(field(details, 'vehicle') || (field(details, 'from') && field(details, 'to')));
}

/** "1晚1间"；缺项省略。 */
function nightsRooms(details: Details): string {
  const nights = field(details, 'nights');
  const rooms = field(details, 'rooms');
  return `${nights ? `${nights}晚` : ''}${rooms ? `${rooms}间` : ''}`;
}

function stayRange(details: Details, joiner: string, withSuffix: boolean): string {
  const checkIn = shortDate(field(details, 'check_in'));
  const checkOut = shortDate(field(details, 'check_out'));
  if (checkIn && checkOut) return withSuffix ? `${checkIn} 入住${joiner}${checkOut} 离店` : `${checkIn}${joiner}${checkOut}`;
  if (checkIn) return `${checkIn} 入住`;
  return checkOut ? `${checkOut} 离店` : '';
}

/** 酒店订单 · 酒店 · 08-15 至 08-16 · 1晚1间 · ¥720.00 · 携程 · 订单号 …006095 */
export function hotelBookingParts(evidence: EvidenceData, orderNoTail = true): string[] {
  const { details } = evidence;
  const amount = evidence.amount_cents === null ? '' : formatMoney(evidence.amount_cents, evidence.currency);
  return [
    '酒店订单',
    field(details, 'hotel') || evidence.merchant,
    stayRange(details, ' 至 ', false),
    nightsRooms(details),
    amount,
    field(details, 'platform'),
    orderNoText(evidence.order_no, orderNoTail),
  ].filter(Boolean);
}

/** 火车 G7123 · 上海虹桥 → 苏州园区 · 08-15 · 张三 */
export function transportParts(details: Details): string[] {
  const vehicle = VEHICLE_LABELS[field(details, 'vehicle')] ?? UNKNOWN_VEHICLE_LABEL;
  const number = field(details, 'number');
  const from = field(details, 'from');
  const to = field(details, 'to');
  const route = from || to ? `${from || UNKNOWN_PLACE} → ${to || UNKNOWN_PLACE}` : '';
  return [number ? `${vehicle} ${number}` : vehicle, route, shortDate(field(details, 'date')), field(details, 'passenger')].filter(Boolean);
}

export interface TravelInfo {
  label: '住宿' | '行程';
  text: string;
}

/** 附件的差旅摘要：酒店订单 → 住宿；交通凭证 / 交通票发票 → 行程；其他为 null。 */
export function attachmentTravelInfo(attachment: Attachment): TravelInfo | null {
  const { evidence, invoice } = attachment;
  if (evidence && hasHotelDetails(evidence.details)) return { label: '住宿', text: hotelBookingParts(evidence).join(' · ') };
  if (evidence && hasTransportDetails(evidence.details)) return { label: '行程', text: transportParts(evidence.details).join(' · ') };
  if (invoice && hasTransportDetails(invoice.details)) return { label: '行程', text: transportParts(invoice.details).join(' · ') };
  return null;
}

export function attachmentTravelSummary(attachment: Attachment): string | null {
  return attachmentTravelInfo(attachment)?.text ?? null;
}

/** 住宿信息条：苏州 · 酒店 · 08-15 入住 → 08-16 离店 · 1晚1间 · 入住人 李欣（取第一张酒店订单）。 */
export function lodgingInfoText(attachments: readonly Attachment[]): string | null {
  const evidence = attachments.map((item) => item.evidence).find((item) => item !== null && hasHotelDetails(item.details));
  if (!evidence) return null;
  const { details } = evidence;
  const guest = field(details, 'guest');
  return [
    field(details, 'city'),
    field(details, 'hotel') || evidence.merchant,
    stayRange(details, ' → ', true),
    nightsRooms(details),
    guest ? `入住人 ${guest}` : '',
  ].filter(Boolean).join(' · ');
}
