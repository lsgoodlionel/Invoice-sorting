import { describe, expect, test } from 'vitest';
import { makeAttachment, makeEvidence, makeHotelEvidence, makeInvoice, makeTransportInvoice, TRAIN_DETAILS } from '../test/fixtures';
import {
  attachmentTravelSummary,
  hasHotelDetails,
  hasTransportDetails,
  hotelBookingParts,
  lodgingInfoText,
  orderNoText,
  shortDate,
  transportParts,
  VEHICLE_LABELS,
} from './travelDetails';

describe('travel detail helpers', () => {
  test('shortDate keeps MM-DD of an ISO date and passes other text through', () => {
    expect(shortDate('2026-08-15')).toBe('08-15');
    expect(shortDate('8月15日')).toBe('8月15日');
    expect(shortDate(undefined)).toBe('');
  });

  test('orderNoText shows tail when requested', () => {
    expect(orderNoText('1132548283006095', true)).toBe('订单号 …006095');
    expect(orderNoText('123', true)).toBe('订单号 123');
    expect(orderNoText('', true)).toBe('');
  });

  test('detects hotel and transport details', () => {
    expect(hasHotelDetails(makeHotelEvidence().details)).toBe(true);
    expect(hasHotelDetails(null)).toBe(false);
    expect(hasHotelDetails({ city: '苏州' })).toBe(false);
    expect(hasTransportDetails(TRAIN_DETAILS)).toBe(true);
    expect(hasTransportDetails({ from: '上海', to: '苏州' })).toBe(true);
    expect(hasTransportDetails({ vehicle: '' })).toBe(false);
    expect(hasTransportDetails(undefined)).toBe(false);
  });
});

describe('hotel booking summary', () => {
  test('full hotel order text', () => {
    expect(hotelBookingParts(makeHotelEvidence()).join(' · ')).toBe(
      '酒店订单 · 苏州园区阳澄湖泰康万豪酒店 · 08-15 至 08-16 · 1晚1间 · ¥720.00 · 携程 · 订单号 …006095',
    );
  });

  test('missing fields are skipped; hotel falls back to merchant', () => {
    const evidence = makeHotelEvidence({
      amount_cents: null, order_no: '', merchant: '某酒店',
      details: { check_in: '2026-08-15', check_out: '', nights: '2', rooms: '', platform: '' },
    });
    expect(hotelBookingParts(evidence)).toEqual(['酒店订单', '某酒店', '08-15 入住', '2晚']);
  });
});

describe('transport summary', () => {
  test('train ticket text with vehicle mapping', () => {
    expect(transportParts(TRAIN_DETAILS).join(' · ')).toBe('火车 G7123 · 上海虹桥 → 苏州园区 · 08-15 · 张三');
  });

  test('all vehicle labels and unknown vehicle', () => {
    expect(VEHICLE_LABELS).toEqual({ train: '火车', flight: '飞机', bus: '汽车', ship: '轮船' });
    expect(transportParts({ vehicle: 'flight', number: 'MU5101', from: '北京', to: '上海' })).toEqual(['飞机 MU5101', '北京 → 上海']);
    expect(transportParts({ vehicle: 'ship', from: '上海' })).toEqual(['轮船', '上海 → ？']);
    expect(transportParts({ vehicle: 'rocket', number: 'X1' })).toEqual(['交通 X1']);
  });
});

describe('attachmentTravelSummary', () => {
  test('hotel evidence, transport evidence and transport invoice', () => {
    expect(attachmentTravelSummary(makeAttachment({ kind: 'order', evidence: makeHotelEvidence() }))).toMatch(/^酒店订单 · 苏州园区/);
    const ticket = makeAttachment({ kind: 'transport', evidence: makeEvidence({ recognizer: 'transport_booking', details: { ...TRAIN_DETAILS } }) });
    expect(attachmentTravelSummary(ticket)).toBe('火车 G7123 · 上海虹桥 → 苏州园区 · 08-15 · 张三');
    expect(attachmentTravelSummary(makeAttachment({ invoice: makeTransportInvoice() }))).toBe('火车 G7123 · 上海虹桥 → 苏州园区 · 08-15 · 张三');
  });

  test('null when no travel details', () => {
    expect(attachmentTravelSummary(makeAttachment({ invoice: makeInvoice() }))).toBeNull();
    expect(attachmentTravelSummary(makeAttachment({ evidence: makeEvidence() }))).toBeNull();
    expect(attachmentTravelSummary(makeAttachment())).toBeNull();
  });
});

describe('lodgingInfoText', () => {
  test('uses the first hotel order in the record', () => {
    const attachments = [makeAttachment({ id: 1, invoice: makeInvoice() }), makeAttachment({ id: 2, kind: 'order', evidence: makeHotelEvidence() })];
    expect(lodgingInfoText(attachments)).toBe('苏州 · 苏州园区阳澄湖泰康万豪酒店 · 08-15 入住 → 08-16 离店 · 1晚1间 · 入住人 李欣');
  });

  test('null without hotel order; partial details are skipped', () => {
    expect(lodgingInfoText([makeAttachment({ invoice: makeInvoice() })])).toBeNull();
    const partial = makeHotelEvidence({ details: { hotel: '某酒店', check_in: '2026-08-15' } });
    expect(lodgingInfoText([makeAttachment({ kind: 'order', evidence: partial })])).toBe('某酒店 · 08-15 入住');
  });
});
