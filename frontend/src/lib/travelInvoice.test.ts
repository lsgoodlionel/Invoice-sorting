import { describe, expect, test } from 'vitest';
import { makeAttachment, makeEvidence, makeInvoice, makeLodgingInvoice, makeTransportInvoice } from '../test/fixtures';
import {
  amountComposition,
  classifyInvoice,
  invoiceMixProblem,
  invoicesTotalCents,
  isLodgingInvoice,
  isTransportInvoice,
} from './travelInvoice';

describe('invoice classification', () => {
  test('transport invoice by details.vehicle or keywords', () => {
    expect(isTransportInvoice(makeTransportInvoice())).toBe(true);
    expect(isTransportInvoice(makeInvoice({ details: { vehicle: 'flight' } }))).toBe(true);
    expect(isTransportInvoice(makeInvoice({ tax_category: '客运服务' }))).toBe(true);
    expect(isTransportInvoice(makeInvoice({ item_summary: '机票款' }))).toBe(true);
    expect(isTransportInvoice(makeInvoice({ item_summary: '汽车票' }))).toBe(true);
    expect(isTransportInvoice(makeInvoice())).toBe(false);
  });

  test('lodging invoice by tax category, item or seller', () => {
    expect(isLodgingInvoice(makeLodgingInvoice())).toBe(true);
    expect(isLodgingInvoice(makeInvoice({ seller_name: '如家宾馆' }))).toBe(true);
    expect(isLodgingInvoice(makeInvoice({ item_summary: '民宿房费' }))).toBe(true);
    expect(isLodgingInvoice(makeInvoice())).toBe(false);
  });

  test('classifyInvoice prefers transport over lodging keywords', () => {
    expect(classifyInvoice(makeTransportInvoice({ seller_name: '酒店班车公司' }))).toBe('transport');
    expect(classifyInvoice(makeLodgingInvoice())).toBe('lodging');
    expect(classifyInvoice(makeInvoice())).toBe('other');
    expect(classifyInvoice(null)).toBe('other');
  });
});

describe('invoiceMixProblem', () => {
  test('zero or one invoice is fine', () => {
    expect(invoiceMixProblem([])).toBeNull();
    expect(invoiceMixProblem([makeInvoice()])).toBeNull();
  });

  test('one lodging plus transport invoices is allowed', () => {
    expect(invoiceMixProblem([makeLodgingInvoice(), makeTransportInvoice(), makeTransportInvoice()])).toBeNull();
  });

  test('two lodging invoices are rejected', () => {
    expect(invoiceMixProblem([makeLodgingInvoice(), makeLodgingInvoice(), makeTransportInvoice()])).toBe('lodging');
  });

  test('several invoices without lodging are rejected', () => {
    expect(invoiceMixProblem([makeTransportInvoice(), makeTransportInvoice()])).toBe('multiple');
    expect(invoiceMixProblem([makeLodgingInvoice(), makeInvoice()])).toBe('multiple');
    expect(invoiceMixProblem([makeLodgingInvoice(), null])).toBe('multiple');
  });
});

describe('amount composition', () => {
  const lodging = makeAttachment({ id: 1, invoice: makeLodgingInvoice() });
  const train1 = makeAttachment({ id: 2, invoice: makeTransportInvoice({ total_cents: 15250 }) });
  const train2 = makeAttachment({ id: 3, invoice: makeTransportInvoice({ total_cents: 15250 }) });
  const order = makeAttachment({ id: 4, kind: 'order', evidence: makeEvidence() });

  test('invoicesTotalCents sums invoice attachments and skips missing totals', () => {
    expect(invoicesTotalCents([lodging, train1, order])).toBe(87250);
    expect(invoicesTotalCents([makeAttachment({ invoice: makeInvoice({ total_cents: null }) })])).toBeNull();
    expect(invoicesTotalCents([order])).toBeNull();
  });

  test('lodging + transport text, matching the amount', () => {
    expect(amountComposition(102500, [lodging, train1, train2, order])).toEqual({
      text: '¥1,025.00 = 住宿 ¥720.00 + 交通 2 张 ¥305.00',
      invoiceTotalCents: 102500,
      isMismatch: false,
    });
  });

  test('flags mismatch against invoice total', () => {
    expect(amountComposition(100000, [lodging, train1, train2])).toMatchObject({ isMismatch: true, invoiceTotalCents: 102500 });
  });

  test('other invoices are listed and null without transport invoices', () => {
    const other = makeAttachment({ id: 5, invoice: makeInvoice({ total_cents: 1000 }) });
    expect(amountComposition(88250, [lodging, train1, other])?.text).toBe('¥882.50 = 住宿 ¥720.00 + 交通 1 张 ¥152.50 + 其他 ¥10.00');
    expect(amountComposition(72000, [lodging])).toBeNull();
    expect(amountComposition(15250, [train1])?.text).toBe('¥152.50 = 交通 1 张 ¥152.50');
  });

  test('attachments whose kind is not invoice are ignored', () => {
    const relabeled = makeAttachment({ id: 6, kind: 'transport', invoice: makeTransportInvoice() });
    expect(amountComposition(72000, [lodging, relabeled])).toBeNull();
  });
});
