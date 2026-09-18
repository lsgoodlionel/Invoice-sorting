import { describe, expect, test } from 'vitest';
import { makeAttachment, makeDetail, makeEvidence, makeHotelEvidence, makeInvoice, makeTransportInvoice, TRAIN_DETAILS } from '../test/fixtures';
import { attachmentFacts, evidenceParts, isEvidenceRecognized, uploadResultMessage } from './evidence';

describe('evidence summary', () => {
  test('foreign order shows type, date, currency amount, merchant/item and order tail', () => {
    expect(evidenceParts(makeEvidence(), { orderNoTail: true })).toEqual([
      '订单', '2026-06-28', 'US$20.00', 'Apple / Claude Pro - Monthly', '订单号 …QX1234',
    ]);
  });

  test('full order number and skipped empty fields', () => {
    const evidence = makeEvidence({ doc_type: 'payment', currency: 'CNY', amount_cents: 14426, merchant: 'PP*APPLE.COM', item_name: '', order_no: '123', occurred_on: null });
    expect(evidenceParts(evidence)).toEqual(['银行交易', '¥144.26', 'PP*APPLE.COM', '订单号 123']);
    expect(evidenceParts(makeEvidence({ doc_type: 'receipt', amount_cents: null, merchant: '', item_name: '', order_no: '' }))).toEqual(['收据', '2026-06-28']);
    expect(evidenceParts(makeEvidence({ doc_type: 'itinerary', order_no: '' }))[0]).toBe('行程单');
  });

  test('recognized only when evidence exists and type is known', () => {
    expect(isEvidenceRecognized(null)).toBe(false);
    expect(isEvidenceRecognized(makeEvidence({ doc_type: 'unknown' }))).toBe(false);
    expect(isEvidenceRecognized(makeEvidence())).toBe(true);
  });

  test('attachmentFacts for invoice and evidence', () => {
    const invoice = makeAttachment({ invoice: makeInvoice({ invoice_no: '2631', order_no: 'JD1', total_cents: 45900, issued_on: '2026-03-12' }) });
    expect(attachmentFacts(invoice)).toEqual([
      { label: '发票号', value: '2631' },
      { label: '订单号', value: 'JD1' },
      { label: '金额', value: '¥459.00' },
      { label: '日期', value: '2026-03-12' },
    ]);
    const order = makeAttachment({ kind: 'order', evidence: makeEvidence({ cny_cents: 14426 }) });
    expect(attachmentFacts(order)).toEqual([
      { label: '订单号', value: 'MSD3K2L9QX1234' },
      { label: '金额', value: 'US$20.00（¥144.26）' },
      { label: '日期', value: '2026-06-28' },
    ]);
    expect(attachmentFacts(makeAttachment({ kind: 'other' }))).toEqual([]);
  });

  test('uploadResultMessage lists kinds of newest attachments', () => {
    const detail = makeDetail({
      id: 7,
      attachments: [
        makeAttachment({ id: 1, kind_label: '发票' }),
        makeAttachment({ id: 9, kind_label: '支付记录' }),
        makeAttachment({ id: 8, kind_label: '订单明细' }),
      ],
    });
    expect(uploadResultMessage(detail, 2)).toBe('已上传 2 个文件到 #7，识别为：订单明细、支付记录');
    expect(uploadResultMessage({ ...detail, attachments: [makeAttachment({ id: 3, kind_label: '支付记录' }), makeAttachment({ id: 4, kind_label: '支付记录' })] }, 2))
      .toBe('已上传 2 个文件到 #7，识别为：支付记录');
    expect(uploadResultMessage({ ...detail, attachments: [] }, 1)).toBe('已上传 1 个文件到 #7');
  });

  test('hotel order and transport evidence use travel summaries', () => {
    expect(evidenceParts(makeHotelEvidence(), { orderNoTail: true }).join(' · ')).toBe(
      '酒店订单 · 苏州园区阳澄湖泰康万豪酒店 · 08-15 至 08-16 · 1晚1间 · ¥720.00 · 携程 · 订单号 …006095',
    );
    const ticket = makeEvidence({ doc_type: 'unknown', recognizer: 'transport_booking', details: { ...TRAIN_DETAILS } });
    expect(evidenceParts(ticket).join(' · ')).toBe('火车 G7123 · 上海虹桥 → 苏州园区 · 08-15 · 张三');
    expect(isEvidenceRecognized(ticket)).toBe(true);
  });

  test('attachmentFacts appends travel summary', () => {
    const facts = attachmentFacts(makeAttachment({ invoice: makeTransportInvoice() }));
    expect(facts.at(-1)).toEqual({ label: '行程', value: '火车 G7123 · 上海虹桥 → 苏州园区 · 08-15 · 张三' });
    const hotel = attachmentFacts(makeAttachment({ kind: 'order', evidence: makeHotelEvidence() }));
    expect(hotel.at(-1)?.label).toBe('住宿');
  });
});
