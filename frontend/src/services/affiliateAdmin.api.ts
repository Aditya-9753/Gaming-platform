import { apiClient } from './api'
import type {
  Adjustment, AdminPartnerRow, AffClick, AffDeposit, AffRegistration, AuditRow, BlogPost, Campaign, CommissionPlan, Contact,
  Deal, Faq, IngestEvent, LedgerEntry, Partner, PrMaterial, RiskEvent, SettlementPeriod, Source, Statement, StatRow,
  TermsVersion, TrackingDomain, TrackingLink, Wallet, Withdrawal,
} from '../types/affiliate.types'

const A = '/aff/admin'
const get = async <T>(url: string, params?: Record<string, unknown>) => (await apiClient.get<T>(A + url, { params })).data
const post = async <T>(url: string, body?: unknown) => (await apiClient.post<T>(A + url, body ?? {})).data
const patch = async <T>(url: string, body?: unknown) => (await apiClient.patch<T>(A + url, body)).data
const put = async <T>(url: string, body?: unknown) => (await apiClient.put<T>(A + url, body)).data
const download = async (url: string, params?: Record<string, unknown>) =>
  (await apiClient.get<Blob>(A + url, { params, responseType: 'blob' })).data

export interface PartnerDetail {
  partner: Partner
  name: string | null
  email_verified: boolean
  two_factor_enabled: boolean
  manager: { id: string; name: string; email: string | null } | null
  profile: Record<string, string | null>
  wallet: Wallet
  deal: Deal | null
  deal_history: Deal[]
  links: TrackingLink[]
  sources: Source[]
  campaigns: Campaign[]
  subpartners: Partner[]
  withdrawals: Withdrawal[]
  stats: Record<string, string | number | null>
  invite_link: string | null
}

export interface Overview {
  partners: Record<string, number>
  open_withdrawals: { count: number; amount: string }
  failed_ingest: number
  open_risk_events: number
  pending_adjustments: number
  balances: { available: string; pending: string; reserved: string }
  current_period: SettlementPeriod
  this_month: StatRow[]
}

export const affAdminApi = {
  overview: () => get<Overview>('/overview'),

  partners: (params: Record<string, unknown>) => get<{ total: number; items: AdminPartnerRow[] }>('/partners', params),
  createPartner: (body: Record<string, unknown>) => post<{ partner: Partner; default_link: TrackingLink }>('/partners', body),
  partner: (id: number) => get<PartnerDetail>(`/partners/${id}`),
  updatePartner: (id: number, body: Record<string, unknown>) => patch<Partner>(`/partners/${id}`, body),
  setStatus: (id: number, status: string, reason?: string) => post<Partner>(`/partners/${id}/status`, { status, reason }),
  impersonate: (id: number) => post<{ access_token: string; expires_in: number; partner_code: string }>(`/partners/${id}/impersonate`),
  changeDeal: (id: number, body: Record<string, unknown>) => post<Deal>(`/partners/${id}/deal`, body),
  ledger: (id: number, cursor?: number) => get<{ wallet: Wallet; items: LedgerEntry[]; next_cursor: number | null }>(`/partners/${id}/ledger`, { cursor }),
  freeze: (id: number, frozen: boolean, reason: string) => post(`/partners/${id}/freeze`, { frozen, reason }),
  staff: () => get<{ items: Array<{ id: string; name: string; email: string | null }> }>('/staff'),
  manualAttribution: (body: Record<string, unknown>) => post<AffRegistration>('/attribution/manual', body),

  links: (params: Record<string, unknown>) => get<{ items: TrackingLink[] }>('/tracking-links', params),
  createLink: (partnerId: number, body: Record<string, unknown>) => post<TrackingLink>(`/partners/${partnerId}/tracking-links`, body),
  updateLink: (id: number, body: Record<string, unknown>) => patch<TrackingLink>(`/tracking-links/${id}`, body),
  sources: (partner_id?: number) => get<{ items: Source[] }>('/sources', { partner_id }),
  updateSource: (id: number, body: Record<string, unknown>) => patch<Source>(`/sources/${id}`, body),
  campaigns: (partner_id?: number) => get<{ items: Campaign[] }>('/campaigns', { partner_id }),
  updateCampaign: (id: number, body: Record<string, unknown>) => patch<Campaign>(`/campaigns/${id}`, body),

  domains: () => get<{ items: TrackingDomain[]; link_base: string }>('/tracking-domains'),
  addDomain: (body: Record<string, unknown>) => post<TrackingDomain>('/tracking-domains', body),
  editDomain: (id: number, body: Record<string, unknown>) => patch<TrackingDomain>(`/tracking-domains/${id}`, body),
  checkDomain: (id: number) => post<TrackingDomain>(`/tracking-domains/${id}/check`),

  plans: () => get<{ items: CommissionPlan[] }>('/plans'),
  createPlan: (body: Record<string, unknown>) => post<CommissionPlan>('/plans', body),
  updatePlan: (id: number, body: Record<string, unknown>) => put<CommissionPlan>(`/plans/${id}`, body),
  deals: () => get<{ items: Array<Deal & { partner_id: number; partner_code: string }> }>('/deals'),

  statistics: (params: Record<string, unknown>) => get<{ items: StatRow[] }>('/statistics', params),
  statisticsCsv: (params: Record<string, unknown>) => download('/statistics/export', params),
  rebuildAnalytics: (days: number) => post<{ rows: number }>(`/analytics/rebuild?days=${days}`),

  periods: () => get<{ items: SettlementPeriod[] }>('/periods'),
  preview: (id: number) => get<{ period: SettlementPeriod; total_to_settle: string; held_total: string; partners: Array<{ partner_id: number; partner_code: string; cpa: string; revshare: string; held: string; count: number }> }>(`/periods/${id}/preview`),
  closePeriod: (id: number) => post<{ period_id: number; statements: number; auto_withdrawals: number }>(`/periods/${id}/close`),
  reopenPeriod: (id: number, reason: string) => post<SettlementPeriod>(`/periods/${id}/reopen`, { reason }),
  statements: (id: number) => get<{ items: Statement[] }>(`/periods/${id}/statements`),

  wallets: (params: Record<string, unknown>) => get<{ items: Array<Wallet & { partner_id: number; partner_code: string; payout_frozen: boolean }> }>('/wallets', params),
  reconcile: () => post<{ mismatches: unknown[] }>('/wallets/reconcile'),
  commissions: (params: Record<string, unknown>) => get<{ items: Array<Record<string, unknown>> }>('/commissions', params),

  withdrawals: (params: Record<string, unknown>) => get<{ items: Withdrawal[] }>('/withdrawals', params),
  withdrawal: (id: number) => get<Withdrawal>(`/withdrawals/${id}`),
  withdrawalAction: (id: number, action: string, body: Record<string, unknown> = {}) => post<Withdrawal>(`/withdrawals/${id}/${action}`, body),
  withdrawalsCsv: (status: string) => download('/withdrawals/export', { status }),

  adjustments: (status?: string) => get<{ items: Adjustment[] }>('/adjustments', { status }),
  requestAdjustment: (body: Record<string, unknown>) => post<Adjustment>('/adjustments', body),
  decideAdjustment: (id: number, approve: boolean, note?: string) => post<Adjustment>(`/adjustments/${id}/decide`, { approve, note }),

  riskEvents: (params: Record<string, unknown>) => get<{ items: RiskEvent[] }>('/risk-events', params),
  reviewRisk: (id: number, status: string, note?: string) => post<RiskEvent>(`/risk-events/${id}/review`, { status, note }),
  depositFraud: (id: number, reason: string) => post<AffDeposit>(`/deposits/${id}/fraud`, { reason }),
  registrationFraud: (id: number, reason: string) => post<AffRegistration>(`/registrations/${id}/fraud`, { reason }),
  clickFraud: (clickId: string, reason: string) => post<AffClick>(`/clicks/${clickId}/fraud`, { reason }),
  ipFraud: (body: Record<string, unknown>) => post<{ marked: number }>('/clicks/fraud-by-ip', body),
  clicks: (partner_id: number) => get<{ items: AffClick[] }>('/clicks', { partner_id }),
  registrations: (partner_id?: number) => get<{ items: AffRegistration[] }>('/registrations', { partner_id }),
  deposits: (params: Record<string, unknown>) => get<{ items: AffDeposit[] }>('/deposits', params),

  ingestEvents: (params: Record<string, unknown>) => get<{ items: IngestEvent[]; next_cursor: number | null; counts: Record<string, number> }>('/ingest-events', params),
  ingestEvent: (id: number) => get<IngestEvent>(`/ingest-events/${id}`),
  retryIngest: (id: number) => post<IngestEvent>(`/ingest-events/${id}/retry`),
  ingestCsv: (event_type: string, csv: string) => post<Record<string, number>>('/ingest/csv', { event_type, csv }),
  fxRates: () => get<{ items: Array<{ rate_date: string; currency: string; rate_to_usd: string }>; fallback: Record<string, string> }>('/fx-rates'),
  setFxRate: (body: Record<string, unknown>) => post('/fx-rates', body),
  syncFx: () => post<{ date: string; currencies: number }>('/fx-rates/sync'),

  materials: () => get<{ items: PrMaterial[] }>('/pr-materials'),
  createMaterial: (body: Record<string, unknown>) => post<PrMaterial>('/pr-materials', body),
  updateMaterial: (id: number, body: Record<string, unknown>) => put<PrMaterial>(`/pr-materials/${id}`, body),
  faqs: () => get<{ items: Faq[] }>('/faqs'),
  createFaq: (body: Record<string, unknown>) => post<Faq>('/faqs', body),
  updateFaq: (id: number, body: Record<string, unknown>) => put<Faq>(`/faqs/${id}`, body),
  blog: () => get<{ items: BlogPost[] }>('/blog-posts'),
  createBlog: (body: Record<string, unknown>) => post<BlogPost>('/blog-posts', body),
  updateBlog: (id: number, body: Record<string, unknown>) => put<BlogPost>(`/blog-posts/${id}`, body),
  contacts: (status?: string) => get<{ items: Contact[] }>('/contacts', { status }),
  replyContact: (id: number, body: Record<string, unknown>) => patch<Contact>(`/contacts/${id}`, body),

  terms: () => get<{ items: TermsVersion[] }>('/terms'),
  publishTerms: (body: Record<string, unknown>) => post<TermsVersion>('/terms', body),
  settings: () => get<{ values: Record<string, unknown>; descriptions: Record<string, string> }>('/settings'),
  saveSettings: (changes: Record<string, unknown>) => put<{ values: Record<string, unknown>; descriptions: Record<string, string> }>('/settings', { changes }),
  auditLogs: (params: Record<string, unknown>) => get<{ items: AuditRow[] }>('/audit-logs', params),
}

export const saveBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
