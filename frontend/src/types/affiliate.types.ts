/** Partner / affiliate platform types (money values are 2-dp strings in USD, e.g. "-218.31"). */

export type PartnerStatus = 'PENDING' | 'ACTIVE' | 'SUSPENDED' | 'BLOCKED'
export type DealType = 'REVSHARE' | 'CPA' | 'HYBRID' | 'TIERED'
export type RecordStatus = 'ACTIVE' | 'PAUSED' | 'ARCHIVED'
export type WithdrawalStatus =
  | 'PENDING' | 'UNDER_REVIEW' | 'APPROVED' | 'PROCESSING' | 'COMPLETED' | 'REJECTED' | 'CANCELLED' | 'FAILED'
export type MethodType = 'EWALLET_EMAIL' | 'USDT_TRC20' | 'BANK' | 'UPI' | 'OTHER'
export type PeriodPreset = 'today' | 'yesterday' | '7d' | '30d' | 'this_month' | 'last_month' | 'all' | 'custom'

export interface Partner {
  id: number
  partner_code: string
  email: string | null
  status: PartnerStatus
  signup_source: 'SELF' | 'ADMIN'
  parent_partner_id: number | null
  manager_id: string | null
  subpartner_rate: string
  payout_frozen: boolean
  timezone: string
  locale: string
  approved_at: string | null
  created_at: string
}

export interface Deal {
  id: number
  plan_id: number | null
  deal_type: DealType
  revshare_rate: string
  cpa_amount: string
  min_ftd_amount: string
  cpa_geo_list: string[] | null
  carryover: boolean
  carryover_cap: string | null
  hold_days: number
  tier_table: Array<{ min_ngr: string; rate: string }> | null
  effective_from: string
  effective_to: string | null
}

export interface Wallet {
  currency: string
  available: string
  pending: string
  reserved: string
  status: 'ACTIVE' | 'FROZEN'
}

export interface TermsVersion {
  id: number
  version: string
  content_url: string | null
  published_at: string
  content?: string | null
}

export interface PartnerMe {
  partner: Partner
  profile: Record<string, string | null>
  name: string
  email_verified: boolean
  wallet: Wallet
  deal: Deal | null
  terms_required: TermsVersion | null
  unread_notifications: number
  impersonated_by: string | null
  is_subpartner: boolean
  subpartners_enabled: boolean
  config: { app_android_url: string; app_ios_url: string; languages: string[]; min_payout: string; cookie_days: number }
}

export interface Kpis {
  period: PeriodPreset
  from: string | null
  to: string | null
  timezone: string
  deal: { type: DealType | null; revshare_rate: string | null }
  transitions: number
  registrations: number
  first_deposits: number
  deposit_count: number
  ratio_registrations: string | null
  ratio_deposits: string | null
  amount_deposit: string
  cost_transition: string | null
  avg_player_income: string | null
  income: string
  sub_commission: string
  ngr: string
  unique_clicks: number
}

export interface SeriesPoint {
  date: string
  referrals: number
  registrations: number
  income: string
  first_deposits: number
  deposit_amount: string
}

export interface FilterOptions {
  sources: Array<{ id: number; name: string }>
  links: Array<{ id: number; name: string; code: string; source_id: number }>
  countries: string[]
}

export interface Source {
  id: number
  partner_id: number
  name: string
  type: string
  url: string | null
  description: string | null
  is_default: boolean
  status: RecordStatus
  created_at: string
}

export interface Campaign {
  id: number
  partner_id: number
  source_id: number
  name: string
  code: string
  destination_url: string | null
  blocked_countries: string[]
  status: RecordStatus
  start_at: string | null
  end_at: string | null
}

export interface TrackingLink {
  id: number
  partner_id: number
  source_id: number
  campaign_id: number | null
  link_code: string
  name: string
  destination_url: string | null
  is_default: boolean
  status: RecordStatus
  urls: { query?: string; redirect?: string }
  created_at: string
}

export interface PromoCode { id: number; tracking_link_id: number; code: string; status: RecordStatus; created_at: string }
export interface QrCode { id: number; tracking_link_id: number; name: string; image_url: string; created_at: string }

export interface PrMaterial {
  id: number
  partner_id: number | null
  campaign_id: number | null
  type: 'BANNER' | 'LANDING' | 'VIDEO' | 'TEXT'
  title: string
  description: string | null
  file_url: string | null
  body_text: string | null
  width: number | null
  height: number | null
  language: string
  geo: string[]
  status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'
  created_at: string
}

export interface StatRow {
  key: string | number
  label: string
  clicks: number
  registrations: number
  first_deposits: number
  deposit_count?: number
  deposit_amount: string
  ngr?: string
  income: string
  ratio_registrations?: string | null
  cost_transition?: string | null
}

export interface SubpartnerRow {
  partner_code: string
  email_masked: string
  status: PartnerStatus
  joined_at: string | null
  clicks: number
  registrations: number
  first_deposits: number
  income: string
  your_commission: string
}

export interface LedgerEntry {
  id: number
  type: string
  bucket: 'PENDING' | 'AVAILABLE' | 'RESERVED'
  direction: 'CREDIT' | 'DEBIT'
  amount: string
  balance_after: string
  reference_type: string | null
  reference_id: string | null
  description: string | null
  created_at: string
}

export interface WithdrawalMethod {
  id: number
  type: MethodType
  label: string
  account_name: string | null
  destination: string
  is_default: boolean
  verified: boolean
  usable_after: string
  status: RecordStatus
  created_at: string
}

export interface Withdrawal {
  id: number
  partner_id: number
  method_id: number
  source: 'MANUAL' | 'AUTO'
  amount: string
  fee: string
  net_amount: string
  currency: string
  status: WithdrawalStatus
  destination: string
  requested_at: string
  approved_at: string | null
  processed_at: string | null
  rejection_reason: string | null
  external_payment_reference: string | null
  history?: Array<{ from: string | null; to: string; changed_by: string | null; note: string | null; at: string }>
  partner_code?: string
  payout_frozen?: boolean
}

export interface WalletView extends Wallet {
  deal: Deal | null
  min_payout: string
  can_withdraw: boolean
  withdraw_blocked_reason: string | null
}

export interface Statement {
  partner_id: number
  period_id: number
  opening_balance: string
  cpa_total: string
  revshare_total: string
  sub_commission_total: string
  adjustments_total: string
  withdrawals_total: string
  carryover_in: string
  writeoff: string
  closing_balance: string
  period?: SettlementPeriod
  partner_code?: string
}

export interface SettlementPeriod {
  id: number
  period_type: 'WEEKLY' | 'MONTHLY'
  start_date: string
  end_date: string
  status: 'OPEN' | 'CLOSING' | 'CLOSED'
  closed_at: string | null
  closed_by: string | null
  reopened_at: string | null
}

export interface Postback { id: number; event_type: 'REGISTRATION' | 'FTD' | 'DEPOSIT'; url_template: string; status: RecordStatus; created_at: string }
export interface PostbackLog { id: number; postback_id: number; event_ref: string; url_sent: string; response_code: number | null; status: string; attempts: number; sent_at: string | null; created_at: string }

export interface Faq { id: number; question: string; answer: string; category: string | null; language: string; status: string; sort_order: number }
export interface BlogPost { id: number; title: string; slug: string; excerpt: string | null; cover_image: string | null; language: string; status: string; published_at: string | null; created_at: string; content?: string }
export interface Contact { id: number; partner_id: number | null; name: string; email: string; subject: string; message: string; reply: string | null; status: 'NEW' | 'IN_PROGRESS' | 'CLOSED'; assigned_to: string | null; created_at: string; updated_at: string; partner_code?: string | null }
export interface PartnerNotification { id: string; title: string; message: string; type: string; is_read: boolean; created_at: string }
export interface ExportJob { id: number; type: string; params: Record<string, unknown>; status: 'PENDING' | 'DONE' | 'FAILED'; row_count: number; error: string | null; created_at: string }

// ----- admin

export interface CommissionPlan {
  id: number
  name: string
  deal_type: DealType
  default_revshare_rate: string
  default_cpa_amount: string
  min_ftd_amount: string
  hold_days: number
  carryover: boolean
  tier_table: Array<{ min_ngr: string; rate: string }> | null
  description: string | null
  status: RecordStatus
}

export interface TrackingDomain { id: number; domain: string; is_primary: boolean; status: 'ACTIVE' | 'INACTIVE' | 'BLOCKED'; ssl_ok: boolean | null; last_checked_at: string | null; last_check_error: string | null }
export interface AdminPartnerRow extends Partner { wallet: Wallet | null; deal: Deal | null }
export interface Adjustment { id: number; partner_id: number; partner_code?: string; direction: 'CREDIT' | 'DEBIT'; amount: string; reason: string; requested_by: string; approved_by: string | null; status: 'PENDING' | 'APPROVED' | 'REJECTED'; decision_note: string | null; decided_at: string | null; created_at: string }
export interface RiskEvent { id: number; partner_id: number | null; customer_id: number | null; event_type: string; risk_score: number; severity: 'LOW' | 'MEDIUM' | 'HIGH'; reason: string; metadata: Record<string, unknown> | null; status: 'OPEN' | 'REVIEWED' | 'CONFIRMED' | 'DISMISSED'; reviewed_by: string | null; reviewed_at: string | null; created_at: string }
export interface IngestEvent { id: number; event_type: string; idempotency_key: string; source: string; signature_ok: boolean; status: 'RECEIVED' | 'PROCESSED' | 'FAILED' | 'IGNORED'; error: string | null; result_ref: string | null; attempts: number; received_at: string; processed_at: string | null; payload?: unknown }
export interface AffDeposit { id: number; customer_id: number; partner_id: number | null; external_transaction_id: string; amount: string; currency: string; amount_usd: string; status: string; is_first_deposit: boolean; qualified_for_cpa: boolean; is_fraud: boolean; completed_at: string | null }
export interface AffRegistration { id: number; customer_id: number; external_customer_id: string | null; partner_id: number; tracking_link_id: number | null; attribution_type: string; click_id: string | null; country: string | null; registered_at: string; status: string }
export interface AffClick { click_id: string; clicked_at: string; partner_id: number; tracking_link_id: number; country: string | null; device_type: string | null; browser: string | null; os: string | null; ip_hash: string | null; sub1: string | null; is_bot: boolean; is_unique: boolean; is_fraud: boolean }
export interface AuditRow { id: string; actor: string; action: string; target_type: string; target_id: string | null; details: Record<string, unknown> | null; ip: string | null; created_at: string }
