import { usePartnerStore } from './partner.store'

/** Partner portal strings. Add a language by adding a dictionary with the same keys. */
const en = {
  dashboard: 'Dashboard', prTools: 'PR Tools', sources: 'Sources', statistics: 'Statistics', common: 'Common',
  subpartners: 'Subpartners', withdrawal: 'Withdrawal', faq: 'FAQ', contacts: 'Contacts', blog: 'Blog', exit: 'Exit',
  profile: 'Profile', notifications: 'Notifications', wallet: 'Wallet', language: 'Language',
  forAllTime: 'For all time', today: 'Today', yesterday: 'Yesterday', last7: 'Last 7 days', last30: 'Last 30 days',
  thisMonth: 'This month', lastMonth: 'Last month', custom: 'Custom range',
  transition: 'Transition', registration: 'Registration', firstDeposits: 'First Deposits', numberDeposits: 'Number deposits',
  ratioRegistrations: 'Ratio on registrations', ratioDeposits: 'Ratio on deposits', amountDeposit: 'Amount deposit',
  costTransition: 'Cost transition', avgPlayerIncome: 'Average player income', income: 'Income',
  referrals: 'Referrals', registrations: 'Registrations', amountDeposits: 'Amount of deposits',
  allSources: 'All sources', allLinks: 'All links', allCountries: 'All countries', apply: 'Apply',
  available: 'Available', pending: 'Pending', reserved: 'Reserved', withdraw: 'Withdraw', amount: 'Amount',
  autoWithdrawal: 'Auto-withdrawal', history: 'History', requested: 'Requested', processed: 'Processed',
  revshare: 'Revshare', cpa: 'CPA', hybrid: 'Hybrid', tiered: 'Tiered',
  save: 'Save', cancel: 'Cancel', copy: 'Copy', copied: 'Copied', create: 'Create', next: 'Next', back: 'Back',
  loading: 'Loading…', noData: 'No data yet', retry: 'Retry',
  pendingApproval: 'Your account is waiting for approval', verifyEmail: 'Confirm your email address',
  suspended: 'Your partner account is suspended',
}

type Dict = typeof en

const hi: Dict = {
  dashboard: 'डैशबोर्ड', prTools: 'प्रचार सामग्री', sources: 'स्रोत', statistics: 'आंकड़े', common: 'सामान्य',
  subpartners: 'सब-पार्टनर', withdrawal: 'निकासी', faq: 'सवाल-जवाब', contacts: 'संपर्क', blog: 'ब्लॉग', exit: 'बाहर निकलें',
  profile: 'प्रोफ़ाइल', notifications: 'सूचनाएं', wallet: 'वॉलेट', language: 'भाषा',
  forAllTime: 'पूरे समय के लिए', today: 'आज', yesterday: 'कल', last7: 'पिछले 7 दिन', last30: 'पिछले 30 दिन',
  thisMonth: 'इस महीने', lastMonth: 'पिछले महीने', custom: 'अपनी तारीखें',
  transition: 'क्लिक', registration: 'रजिस्ट्रेशन', firstDeposits: 'पहली जमा', numberDeposits: 'जमा की संख्या',
  ratioRegistrations: 'क्लिक प्रति रजिस्ट्रेशन', ratioDeposits: 'जमा प्रति रजिस्ट्रेशन', amountDeposit: 'कुल जमा',
  costTransition: 'कमाई प्रति क्लिक', avgPlayerIncome: 'प्रति खिलाड़ी औसत आय', income: 'आय',
  referrals: 'रेफ़रल', registrations: 'रजिस्ट्रेशन', amountDeposits: 'जमा राशि',
  allSources: 'सभी स्रोत', allLinks: 'सभी लिंक', allCountries: 'सभी देश', apply: 'लागू करें',
  available: 'उपलब्ध', pending: 'लंबित', reserved: 'आरक्षित', withdraw: 'निकालें', amount: 'राशि',
  autoWithdrawal: 'ऑटो-निकासी', history: 'इतिहास', requested: 'अनुरोध', processed: 'पूरा',
  revshare: 'रेवशेयर', cpa: 'CPA', hybrid: 'हाइब्रिड', tiered: 'टियर',
  save: 'सेव करें', cancel: 'रद्द करें', copy: 'कॉपी', copied: 'कॉपी हो गया', create: 'बनाएं', next: 'आगे', back: 'पीछे',
  loading: 'लोड हो रहा है…', noData: 'अभी कोई डेटा नहीं', retry: 'फिर कोशिश करें',
  pendingApproval: 'आपका खाता मंज़ूरी की प्रतीक्षा में है', verifyEmail: 'अपना ईमेल पता पक्का करें',
  suspended: 'आपका पार्टनर खाता निलंबित है',
}

const DICTS: Record<string, Dict> = { en, hi }
export const LANGUAGE_NAMES: Record<string, string> = { en: 'EN', hi: 'हिं', ru: 'RU' }
export type TKey = keyof Dict

export function useT() {
  const locale = usePartnerStore((s) => s.locale)
  const dict = DICTS[locale] || en
  return (key: TKey) => dict[key] ?? en[key]
}
