// 导入确认表（按凭证组）：会话 → 可编辑状态（纯 reducer）→ confirm 请求体。
import type {
  Attachment,
  AttachmentKind,
  ConfirmGroup,
  ImportAction,
  ImportConfirmInput,
  ImportGroup,
  ImportSession,
  MatchCandidate,
} from '../api/types';
import { candidateOptionLabel } from './candidates';
import { DEFAULT_CURRENCY, isForeignCurrency } from './money';
import { classifyInvoice, invoiceMixProblem, invoicesTotalCents } from './travelInvoice';

export type OperationChoice =
  | { type: 'create' }
  | { type: 'skip' }
  | { type: 'candidate'; expenseId: number }
  | { type: 'search'; expenseId: number | null };

export interface GroupFields {
  spentOn: string | null;
  amountCents: number | null;
  currency: string;
  originalAmountCents: number | null;
  merchant: string;
  summary: string;
  categoryId: number | null;
  projectId: number | null;
  isOnline: boolean;
  invoiceExempt: boolean;
}

export interface GroupDraft extends GroupFields {
  groupId: string;
  attachmentIds: readonly number[];
  operation: OperationChoice;
  linkReasons: readonly string[];
  warnings: readonly string[];
  match: MatchCandidate | null;
  candidates: readonly MatchCandidate[];
  /** 用户手动改过人民币金额：移动交通票发票时不再自动重算 */
  isAmountEdited: boolean;
}

export interface ImportGroupsState {
  attachments: Readonly<Record<number, Attachment>>;
  /** 用户改过的附件类型（与原类型相同则不记录） */
  kinds: Readonly<Record<number, AttachmentKind>>;
  groups: readonly GroupDraft[];
  splitSeq: number;
}

export type ImportGroupsAction =
  | { type: 'reset'; session: ImportSession }
  | { type: 'updateFields'; groupId: string; patch: Partial<GroupFields> }
  | { type: 'setOperation'; groupId: string; operation: OperationChoice }
  | { type: 'setKind'; attachmentId: number; kind: AttachmentKind }
  | { type: 'moveAttachment'; attachmentId: number; targetGroupId: string }
  | { type: 'splitAttachment'; attachmentId: number };

export const MULTI_INVOICE_PROBLEM = '一组最多一张发票，请把多余的发票移到其他组或拆为单独一组';
export const MULTI_LODGING_PROBLEM = '一组最多一张住宿发票（可另带交通票发票），请把多余的住宿发票移到其他组';

function initialOperation(group: ImportGroup): OperationChoice {
  if (group.suggested_action === 'skip') return { type: 'skip' };
  if (group.suggested_action === 'create') return { type: 'create' };
  const target = group.match ?? group.candidates[0];
  return target ? { type: 'candidate', expenseId: target.expense_id } : { type: 'search', expenseId: null };
}

function draftFromGroup(group: ImportGroup): GroupDraft {
  const { summary } = group;
  return {
    groupId: group.group_id,
    attachmentIds: group.attachments.map((item) => item.id),
    operation: initialOperation(group),
    spentOn: summary.spent_on,
    amountCents: summary.amount_cents,
    currency: summary.currency || DEFAULT_CURRENCY,
    originalAmountCents: summary.original_amount_cents,
    merchant: summary.merchant,
    summary: summary.summary,
    categoryId: summary.category_id,
    projectId: null,
    isOnline: summary.is_online,
    invoiceExempt: summary.invoice_exempt,
    linkReasons: group.link_reasons,
    warnings: group.warnings,
    match: group.match,
    candidates: group.candidates,
    isAmountEdited: false,
  };
}

export function initImportGroups(session: ImportSession): ImportGroupsState {
  const attachments = Object.fromEntries(session.groups.flatMap((group) => group.attachments.map((item) => [item.id, item])));
  return { attachments, kinds: {}, groups: session.groups.map(draftFromGroup), splitSeq: 0 };
}

function mapGroup(state: ImportGroupsState, groupId: string, fn: (group: GroupDraft) => GroupDraft): ImportGroupsState {
  if (!state.groups.some((group) => group.groupId === groupId)) return state;
  return { ...state, groups: state.groups.map((group) => (group.groupId === groupId ? fn(group) : group)) };
}

function applyFields(group: GroupDraft, patch: Partial<GroupFields>): GroupDraft {
  const next = { ...group, ...patch, isAmountEdited: group.isAmountEdited || 'amountCents' in patch };
  return isForeignCurrency(next.currency) ? next : { ...next, currency: DEFAULT_CURRENCY, originalAmountCents: null };
}

function setKind(state: ImportGroupsState, attachmentId: number, kind: AttachmentKind): ImportGroupsState {
  const original = state.attachments[attachmentId]?.kind;
  const rest = Object.fromEntries(Object.entries(state.kinds).filter(([id]) => Number(id) !== attachmentId));
  return { ...state, kinds: kind === original ? rest : { ...rest, [attachmentId]: kind } };
}

function findGroupOf(state: ImportGroupsState, attachmentId: number): GroupDraft | undefined {
  return state.groups.find((group) => group.attachmentIds.includes(attachmentId));
}

function withoutAttachment(groups: readonly GroupDraft[], attachmentId: number): GroupDraft[] {
  return groups
    .map((group) => ({ ...group, attachmentIds: group.attachmentIds.filter((id) => id !== attachmentId) }))
    .filter((group) => group.attachmentIds.length > 0);
}

function moveAttachment(state: ImportGroupsState, attachmentId: number, targetGroupId: string): ImportGroupsState {
  const source = findGroupOf(state, attachmentId);
  const hasTarget = state.groups.some((group) => group.groupId === targetGroupId);
  if (!source || !hasTarget || source.groupId === targetGroupId) return state;
  const groups = state.groups
    .map((group) => (group.groupId === targetGroupId ? { ...group, attachmentIds: [...group.attachmentIds, attachmentId] } : group))
    .map((group) => (group.groupId === source.groupId ? { ...group, attachmentIds: group.attachmentIds.filter((id) => id !== attachmentId) } : group))
    .filter((group) => group.attachmentIds.length > 0);
  return refreshLodgingAmounts({ ...state, groups }, attachmentId, [source.groupId, targetGroupId]);
}

/** 单个文件的识别结果 → 新建记录字段（分类、项目、网购沿用原组）。 */
export function fieldsFromAttachment(attachment: Attachment, base: GroupFields): GroupFields {
  const common = { categoryId: base.categoryId, projectId: base.projectId, isOnline: base.isOnline };
  const { invoice, evidence } = attachment;
  if (invoice) {
    return {
      ...common, spentOn: invoice.issued_on, amountCents: invoice.total_cents, currency: DEFAULT_CURRENCY, originalAmountCents: null,
      merchant: invoice.seller_name, summary: invoice.item_summary, invoiceExempt: false,
    };
  }
  const isForeign = evidence !== null && isForeignCurrency(evidence.currency);
  return {
    ...common,
    spentOn: evidence?.occurred_on ?? null,
    amountCents: evidence?.cny_cents ?? null,
    currency: isForeign ? evidence.currency : DEFAULT_CURRENCY,
    originalAmountCents: isForeign ? evidence.amount_cents : null,
    merchant: evidence?.merchant ?? '',
    summary: evidence?.item_name ?? '',
    invoiceExempt: evidence?.is_foreign ?? false,
  };
}

function nextSplitId(state: ImportGroupsState): { groupId: string; splitSeq: number } {
  const taken = new Set(state.groups.map((group) => group.groupId));
  let splitSeq = state.splitSeq + 1;
  while (taken.has(`split-${splitSeq}`)) splitSeq += 1;
  return { groupId: `split-${splitSeq}`, splitSeq };
}

function splitAttachment(state: ImportGroupsState, attachmentId: number): ImportGroupsState {
  const source = findGroupOf(state, attachmentId);
  const attachment = state.attachments[attachmentId];
  if (!source || !attachment || source.attachmentIds.length < 2) return state;
  const { groupId, splitSeq } = nextSplitId(state);
  const created: GroupDraft = {
    ...fieldsFromAttachment(attachment, source),
    groupId, attachmentIds: [attachmentId], operation: { type: 'create' },
    linkReasons: [], warnings: [], match: null, candidates: [], isAmountEdited: false,
  };
  const remaining = withoutAttachment(state.groups, attachmentId);
  const index = remaining.findIndex((group) => group.groupId === source.groupId);
  const next = { ...state, splitSeq, groups: [...remaining.slice(0, index + 1), created, ...remaining.slice(index + 1)] };
  return refreshLodgingAmounts(next, attachmentId, [source.groupId]);
}

/** 按当前类型（含用户改过的）看待组内附件。 */
function effectiveAttachments(state: ImportGroupsState, group: GroupDraft): Attachment[] {
  return groupAttachments(state, group).map((item) => ({ ...item, kind: effectiveKind(state, item.id) ?? item.kind }));
}

function isTransportInvoiceFile(state: ImportGroupsState, attachmentId: number): boolean {
  const invoice = state.attachments[attachmentId]?.invoice ?? null;
  return effectiveKind(state, attachmentId) === 'invoice' && classifyInvoice(invoice) === 'transport';
}

/** 住宿组金额 = 组内发票价税合计（用户改过金额或外币组不动）。 */
function recalcLodgingAmount(state: ImportGroupsState, group: GroupDraft): GroupDraft {
  if (group.isAmountEdited || isForeignCurrency(group.currency)) return group;
  const attachments = effectiveAttachments(state, group);
  const hasLodging = attachments.some((item) => item.kind === 'invoice' && classifyInvoice(item.invoice) === 'lodging');
  const total = hasLodging ? invoicesTotalCents(attachments) : null;
  return total === null ? group : { ...group, amountCents: total };
}

/** 交通票发票移入/移出住宿组后重算相关组的金额。 */
function refreshLodgingAmounts(state: ImportGroupsState, attachmentId: number, groupIds: readonly string[]): ImportGroupsState {
  if (!isTransportInvoiceFile(state, attachmentId)) return state;
  const groups = state.groups.map((group) => (groupIds.includes(group.groupId) ? recalcLodgingAmount(state, group) : group));
  return { ...state, groups };
}

export function importGroupsReducer(state: ImportGroupsState, action: ImportGroupsAction): ImportGroupsState {
  switch (action.type) {
    case 'reset':
      return initImportGroups(action.session);
    case 'updateFields':
      return mapGroup(state, action.groupId, (group) => applyFields(group, action.patch));
    case 'setOperation':
      return mapGroup(state, action.groupId, (group) => ({ ...group, operation: action.operation }));
    case 'setKind':
      return setKind(state, action.attachmentId, action.kind);
    case 'moveAttachment':
      return moveAttachment(state, action.attachmentId, action.targetGroupId);
    case 'splitAttachment':
      return splitAttachment(state, action.attachmentId);
  }
}

export function effectiveKind(state: ImportGroupsState, attachmentId: number): AttachmentKind | undefined {
  return state.kinds[attachmentId] ?? state.attachments[attachmentId]?.kind;
}

export function groupAttachments(state: ImportGroupsState, group: GroupDraft): Attachment[] {
  return group.attachmentIds.map((id) => state.attachments[id]).filter((item): item is Attachment => item !== undefined);
}

export function invoiceCount(state: ImportGroupsState, group: GroupDraft): number {
  return group.attachmentIds.filter((id) => effectiveKind(state, id) === 'invoice').length;
}

export function actionOf(operation: OperationChoice): ImportAction {
  if (operation.type === 'candidate' || operation.type === 'search') return 'attach';
  return operation.type;
}

const MIX_PROBLEM_TEXT = { lodging: MULTI_LODGING_PROBLEM, multiple: MULTI_INVOICE_PROBLEM } as const;

/** 多发票校验：允许一张住宿发票 + 若干交通票发票。 */
function invoiceProblems(state: ImportGroupsState, group: GroupDraft): string[] {
  const invoices = effectiveAttachments(state, group).filter((item) => item.kind === 'invoice').map((item) => item.invoice);
  const problem = invoiceMixProblem(invoices);
  return problem ? [MIX_PROBLEM_TEXT[problem]] : [];
}

/** 该组的校验问题；为空表示可以确认。 */
export function groupProblems(state: ImportGroupsState, group: GroupDraft): string[] {
  const problems = invoiceProblems(state, group);
  const { operation } = group;
  if (operation.type === 'create') {
    if (!group.spentOn) problems.push('请填写日期');
    if (group.amountCents === null) problems.push('请填写人民币金额');
  }
  if (operation.type === 'search' && operation.expenseId === null) problems.push('请选择要挂到的记录');
  return problems;
}

export interface GroupTally {
  total: number;
  create: number;
  attach: number;
  skip: number;
  invalid: number;
}

export function tallyGroups(state: ImportGroupsState): GroupTally {
  return state.groups.reduce<GroupTally>(
    (tally, group) => {
      const action = actionOf(group.operation);
      const isInvalid = groupProblems(state, group).length > 0;
      return { ...tally, [action]: tally[action] + 1, invalid: tally.invalid + (isInvalid ? 1 : 0) };
    },
    { total: state.groups.length, create: 0, attach: 0, skip: 0, invalid: 0 },
  );
}

function groupKinds(state: ImportGroupsState, group: GroupDraft): Record<string, AttachmentKind> {
  return Object.fromEntries(group.attachmentIds.filter((id) => state.kinds[id]).map((id) => [String(id), state.kinds[id]]));
}

function toConfirmGroup(state: ImportGroupsState, group: GroupDraft): ConfirmGroup {
  const base = { group_id: group.groupId, attachment_ids: [...group.attachmentIds] };
  const { operation } = group;
  if (operation.type === 'skip') return { ...base, action: 'skip' };
  const kinds = groupKinds(state, group);
  const withKinds = Object.keys(kinds).length > 0 ? { ...base, kinds } : base;
  if (operation.type !== 'create') {
    return operation.expenseId === null ? { ...withKinds, action: 'attach' } : { ...withKinds, action: 'attach', expense_id: operation.expenseId };
  }
  return {
    ...withKinds,
    action: 'create',
    spent_on: group.spentOn ?? undefined,
    amount_cents: group.amountCents ?? undefined,
    currency: group.currency,
    original_amount_cents: isForeignCurrency(group.currency) ? group.originalAmountCents : null,
    merchant: group.merchant.trim(),
    summary: group.summary.trim(),
    category_id: group.categoryId,
    project_id: group.projectId,
    is_online: group.isOnline,
    invoice_exempt: group.invoiceExempt,
  };
}

export function buildConfirmInput(state: ImportGroupsState): ImportConfirmInput {
  return { groups: state.groups.map((group) => toConfirmGroup(state, group)) };
}

const EXPENSE_PREFIX = 'expense:';

export function operationValue(operation: OperationChoice): string {
  return operation.type === 'candidate' ? `${EXPENSE_PREFIX}${operation.expenseId}` : operation.type;
}

export function parseOperationValue(value: string): OperationChoice | null {
  if (value === 'create' || value === 'skip') return { type: value };
  if (value === 'search') return { type: 'search', expenseId: null };
  if (!value.startsWith(EXPENSE_PREFIX)) return null;
  const expenseId = Number(value.slice(EXPENSE_PREFIX.length));
  return Number.isInteger(expenseId) && expenseId > 0 ? { type: 'candidate', expenseId } : null;
}

export function operationOptions(group: GroupDraft): { value: string; label: string }[] {
  const all = [...(group.match ? [group.match] : []), ...group.candidates];
  const targets = all.filter((item, index) => all.findIndex((other) => other.expense_id === item.expense_id) === index);
  return [
    { value: 'create', label: '新建记录' },
    ...targets.map((candidate) => ({ value: `${EXPENSE_PREFIX}${candidate.expense_id}`, label: candidateOptionLabel(candidate) })),
    { value: 'search', label: '搜索其他记录…' },
    { value: 'skip', label: '留在待归属' },
  ];
}

/** "组 1 · 京东某店"；没有商家时用第一个文件名。 */
export function groupTitle(state: ImportGroupsState, group: GroupDraft, index: number): string {
  const name = group.merchant.trim() || groupAttachments(state, group)[0]?.original_name || '';
  return [`组 ${index + 1}`, name].filter(Boolean).join(' · ');
}
