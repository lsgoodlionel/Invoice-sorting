import type { Attachment, InvoiceData, BatchDetail, ChecklistItem, ExpenseDetail, ExpenseSummary, ImportRow, Project } from '../api/types';

export function makeExpense(overrides: Partial<ExpenseSummary> = {}): ExpenseSummary {
  return {
    id: 1,
    spent_on: '2026-09-15',
    amount_cents: 96000,
    merchant: '京东某店',
    summary: '鼠标×2',
    category_id: 2,
    category_name: '易耗品',
    category_color: '#1F5F4A',
    project_id: null,
    project_name: null,
    status: 'invoiced',
    status_label: '已开票',
    status_manual: false,
    missing_count: 0,
    batch_id: null,
    batch_name: null,
    attachment_count: 1,
    invoice_no: null,
    region_name: '',
    is_nonlocal: false,
    ...overrides,
  };
}

export function makeAttachment(overrides: Partial<Attachment> = {}): Attachment {
  return {
    id: 10,
    expense_id: 1,
    kind: 'invoice',
    kind_label: '发票',
    original_name: '发票_123.pdf',
    file_name: '发票_123.pdf',
    mime: 'application/pdf',
    size: 20480,
    created_at: '2026-09-15T10:00:00+08:00',
    url: '/api/attachments/10/file',
    invoice: null,
    ...overrides,
  };
}

export function makeInvoice(overrides: Partial<InvoiceData> = {}): InvoiceData {
  return {
    invoice_no: '26312000000123456789',
    issued_on: '2026-09-15',
    total_cents: 96000,
    tax_cents: 11044,
    seller_name: '京东某店',
    seller_tax_id: '91110000000000000X',
    buyer_name: '某大学',
    buyer_tax_id: '12310000000000000Y',
    item_summary: '鼠标',
    invoice_type: '电子发票（普通发票）',
    parser: 'pdf',
    confirmed: false,
    tax_category: '计算机配套产品',
    region_name: '上海',
    is_nonlocal: false,
    order_no: '',
    detail_platform: false,
    buyer_mismatch: false,
    ...overrides,
  };
}

export function makeChecklistItem(overrides: Partial<ChecklistItem> = {}): ChecklistItem {
  return {
    id: 100,
    attachment_kind: 'invoice',
    kind_label: '发票',
    level: 'required',
    state: 'present',
    reason: '',
    hint: '',
    ...overrides,
  };
}

export function makeDetail(overrides: Partial<ExpenseDetail> = {}): ExpenseDetail {
  return {
    ...makeExpense(),
    pay_method: '微信',
    is_online: true,
    note: '',
    void_reason: '',
    sent_on: null,
    reimbursed_on: null,
    reimbursed_cents: 0,
    folder_path: '',
    route_hint: '',
    attachments: [],
    checklist: [],
    timeline: [],
    created_at: '2026-09-15T10:00:00+08:00',
    updated_at: '2026-09-15T10:00:00+08:00',
    ...overrides,
  };
}

export function makeImportRow(overrides: Partial<ImportRow> = {}): ImportRow {
  return {
    row_id: 'r1',
    attachment: makeAttachment({ expense_id: null }),
    is_invoice: true,
    suggested: { spent_on: '2026-09-15', amount_cents: 96000, merchant: '京东某店', summary: '鼠标', category_id: 1, is_online: false },
    match: null,
    warnings: [],
    ...overrides,
  };
}

export function makeBatch(overrides: Partial<BatchDetail> = {}): BatchDetail {
  return {
    id: 5,
    name: '9月第1批',
    project_id: null,
    project_name: null,
    status: 'draft',
    status_label: '待外发',
    sent_on: null,
    sent_via: '',
    receiver: '',
    external_no: '',
    received_on: null,
    received_cents: 0,
    note: '',
    created_at: '2026-09-15T10:00:00+08:00',
    item_count: 0,
    total_cents: 0,
    missing_item_count: 0,
    expenses: [],
    exports: [],
    ...overrides,
  };
}

export function makeProject(overrides: Partial<Project> = {}): Project {
  return { id: 1, code: 'KY-01', name: '科研A', owner: '', active: true, ...overrides };
}
