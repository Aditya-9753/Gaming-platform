import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Lock, Mail, Phone, ShieldAlert, ArrowRight, Eye, EyeOff, Check, X } from 'lucide-react'
import { Input } from '../../components/common/Input'
import { Button } from '../../components/common/Button'
import { useAuthStore } from '../../store/auth.store'
import { authApi } from '../../services/auth.api'
import { showToast } from '../../components/common/toastBus'
import { clearReferral, getReferral } from '../../utils/referral'
import { t as tr } from '../../i18n'
import { useLogoSplash } from '../../components/brand/logoSplashStore'
import { BrandHero } from '../../components/brand/BrandHero'

// Indian mobile number (10 digits, starts 6-9); the server stores it as +91XXXXXXXXXX
const PHONE_PATTERN = /^[6-9]\d{9}$/
// Must match PLAYER_PASSWORD_PATTERN on the server
const passwordChecks = (password: string) => [
  { label: 'At least 8 characters', ok: password.length >= 8 && password.length <= 128 },
  { label: 'At least one letter (a–z or A–Z)', ok: /[A-Za-z]/.test(password) },
  { label: 'At least one number (0–9)', ok: /\d/.test(password) },
]

const getRegistrationError = (error: unknown): string => {
  if (!axios.isAxiosError(error)) return 'Registration could not be completed. Please try again.'

  const body = error.response?.data as {
    error?: { message?: string; details?: Array<{ loc?: Array<string | number>; msg?: string }> }
  } | undefined
  const details = body?.error?.details
  if (Array.isArray(details) && details.length > 0) {
    return details.map((item) => {
      const field = item.loc?.at(-1)
      const message = item.msg?.replace(/^Value error,\s*/i, '')
      if (field === 'password') return 'Password must be at least 8 characters with a letter and a number.'
      if (field === 'phone') return tr('Enter a valid 10-digit Indian mobile number.')
      if (field === 'age_confirmed') return 'Confirm that you meet the legal age requirement.'
      return message || body?.error?.message || tr('Please check your details and try again.')
    }).join(' ')
  }

  if (error.response?.status === 409) return body?.error?.message || tr('This mobile number is already registered. Sign in instead.')
  if (error.response?.status === 429) return 'Too many registration attempts. Please wait a few minutes and try again.'
  if (error.response && error.response.status >= 500) return 'The server could not save your account right now. Please try again in a minute.'
  if (!error.response) return 'Cannot reach the server. Check your internet connection and try again.'
  return body?.error?.message || tr('Registration could not be completed. Please try again.')
}

export const Register: React.FC = () => {
  const navigate = useNavigate()
  const { setAuth, setAccessToken } = useAuthStore()
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [is18, setIs18] = useState(false)
  // Bonus or partner promo code (prefilled from a ?promo= link); the partner click id is sent automatically
  const [promoCode, setPromoCode] = useState(() => getReferral().promo || '')
  const [isLoading, setIsLoading] = useState(false)

  const checks = passwordChecks(password)
  const passwordOk = checks.every((c) => c.ok)

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!PHONE_PATTERN.test(phone)) {
      showToast({ title: tr('Invalid mobile number'), message: tr('Enter your 10-digit mobile number (for example 9876543210).'), type: 'error' })
      return
    }
    if (!passwordOk) {
      showToast({ title: tr('Password too weak'), message: tr('Use at least 8 characters with a letter and a number.'), type: 'error' })
      return
    }
    if (password !== confirmPassword) {
      showToast({ title: tr('Passwords do not match'), message: tr('Re-enter the same password in both fields.'), type: 'error' })
      return
    }
    if (!is18) {
      showToast({ title: tr('Age restriction'), message: tr('You must confirm you are of legal age.'), type: 'error' })
      return
    }
    setIsLoading(true)
    try {
      const { access_token, promo } = await authApi.register('', password, is18, email.trim() || undefined, { click_id: getReferral().click_id, promo_code: promoCode }, `+91${phone}`)
      clearReferral()
      setAccessToken(access_token)
      const user = await authApi.getCurrentUser()
      setAuth(user, access_token)
      useLogoSplash.getState().show()
      if (promo && promo.amount_paise > 0) {
        showToast({ title: tr('Promo bonus added'), message: `₹${(promo.amount_paise / 100).toLocaleString('en-IN')} ${tr('from code')} ${promo.code}`, type: 'success', duration: 7000 })
      } else if (promo?.message) {
        showToast({ title: tr('Account created'), message: `${tr('Promo code')} ${promo.code}: ${promo.message}`, type: 'warning', duration: 9000 })
      } else {
        showToast({ title: tr('Account created'), message: tr('Your account is ready.'), type: 'success' })
      }
      navigate('/')
    } catch (error) {
      showToast({ title: tr('Registration failed'), message: getRegistrationError(error), type: 'error', duration: 9000 })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto py-8">
      <div className="bg-dark-card border border-dark-border rounded-3xl p-8 shadow-2xl space-y-6">
        <div className="text-center space-y-2">
          <BrandHero className="w-36 sm:w-44" />
          <h2 className="text-2xl font-black text-white">{tr('Create Account')}</h2>
          <p className="text-xs text-slate-400">{tr("Your mobile number and a password, that's all you need")}</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label={tr('Mobile number')} type="tel" inputMode="numeric" autoComplete="tel-national" maxLength={10} placeholder="9876543210"
            value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, '').slice(-10))}
            leftElement={<span className="flex items-center gap-1.5 text-sm font-semibold text-slate-300"><Phone className="w-4 h-4 text-slate-400" />+91</span>}
            className="pl-[4.5rem]"
            error={phone.length === 10 && !PHONE_PATTERN.test(phone) ? tr('Indian mobile numbers start with 6, 7, 8 or 9') : undefined}
            helperText={tr('You will sign in with this number')}
            required
          />
          <div className="space-y-2">
            <Input
              label={tr('Password')} type={showPassword ? 'text' : 'password'} autoComplete="new-password" maxLength={128} placeholder={tr('e.g. sanu1234')}
              value={password} onChange={(e) => setPassword(e.target.value)}
              leftElement={<Lock className="w-4 h-4 text-slate-400" />}
              rightElement={<button type="button" onClick={() => setShowPassword((v) => !v)} aria-label={showPassword ? 'Hide password' : 'Show password'} className="text-slate-400 hover:text-white">{showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>}
              required
            />
            <ul className="grid gap-1 text-xs">
              {checks.map((c) => (
                <li key={c.label} className={`flex items-center gap-1.5 ${password ? (c.ok ? 'text-emerald-400' : 'text-rose-400') : 'text-slate-500'}`}>
                  {password && c.ok ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}{tr(c.label)}
                </li>
              ))}
            </ul>
          </div>
          <Input
            label={tr('Confirm password')} type={showPassword ? 'text' : 'password'} autoComplete="new-password" maxLength={128}
            value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
            leftElement={<Lock className="w-4 h-4 text-slate-400" />}
            error={confirmPassword && confirmPassword !== password ? '✗ Passwords do not match' : undefined}
            success={confirmPassword && confirmPassword === password ? '✓ Passwords match' : undefined}
            required
          />
          <Input
            label={tr('Email (optional)')} type="email" autoComplete="email" maxLength={255} placeholder="you@example.com"
            value={email} onChange={(e) => setEmail(e.target.value)}
            leftElement={<Mail className="w-4 h-4 text-slate-400" />}
            helperText={tr('Needed to reset your password if you forget it')}
          />
          <Input
            label={tr('Promo code (optional)')} autoCapitalize="characters" maxLength={32}
            value={promoCode} onChange={(e) => setPromoCode(e.target.value.toUpperCase())}
          />
          <div className="p-3 rounded-xl bg-dark-elevated border border-dark-border">
            <label className="flex items-start gap-2.5 text-xs text-slate-300 cursor-pointer">
              <input type="checkbox" checked={is18} onChange={(e) => setIs18(e.target.checked)} className="mt-0.5 rounded" required />
              <span>{tr('I confirm I am of legal age to use this platform.')}</span>
            </label>
          </div>
          <Button type="submit" variant="primary" className="w-full font-black py-3" isLoading={isLoading} rightIcon={<ArrowRight className="w-4 h-4" />}>{tr('Create My Account')}</Button>
        </form>
        <p className="text-center text-xs text-slate-400">
          {tr('Already have an account?')} <Link to="/login" className="text-emerald-400 font-bold hover:underline">{tr('Sign In')}</Link>
        </p>
        <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-500 text-center">
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          <span>{tr('Age eligibility is required to register.')}</span>
        </div>
      </div>
    </div>
  )
}
