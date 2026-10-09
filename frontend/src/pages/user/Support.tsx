import React, { useEffect, useState } from 'react'
import { Headphones, Plus, MessageCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { Input } from '../../components/common/Input'
import { Button } from '../../components/common/Button'
import { showToast } from '../../components/common/Toast'
import { supportApi } from '../../services/support.api'
import type { SupportTicket } from '../../types/support.types'
import { t as tr } from '../../i18n'

const faqs = [
  {
    q: 'How does the Aviator game work?',
    a: 'Aviator is a multiplayer crash game. A plane takes off and the multiplier climbs. You must cash out before the plane flies away. The multiplier at which you cash out is applied to your bet amount.',
  },
  {
    q: 'How can I verify game fairness?',
    a: 'Every round uses HMAC-SHA256 provably fair cryptography. Before each round starts, the server publishes a hash of its secret seed. After the round, the full seed is revealed so you can independently verify the outcome.',
  },
  {
    q: 'Can I deposit or withdraw money?',
    a: 'Payment deposits and withdrawals are not currently enabled. The wallet uses platform credits only.',
  },
  {
    q: 'How do I contact support?',
    a: 'Open a ticket below. You can follow replies and send messages in the ticket thread.',
  },
]

export const Support: React.FC = () => {
  const [openFaqIdx, setOpenFaqIdx] = useState<number | null>(null)
  const [subject, setSubject] = useState('')
  const [category, setCategory] = useState('deposit')
  const [message, setMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [tickets, setTickets] = useState<SupportTicket[]>([])
  const [selectedTicket, setSelectedTicket] = useState<SupportTicket | null>(null)
  const [reply, setReply] = useState('')
  const [isReplying, setIsReplying] = useState(false)

  useEffect(() => {
    supportApi.getTickets().then(setTickets).catch(() => {
      showToast({ title: tr('Tickets unavailable'), message: tr('Support tickets could not be loaded.'), type: 'error' })
    })
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!subject || !message) {
      showToast({ title: tr('Missing Fields'), message: tr('Subject and message are required.'), type: 'warning' })
      return
    }
    setIsSubmitting(true)
    try {
      const ticket = await supportApi.createTicket({ subject, category, message })
      const detail = await supportApi.getTicket(ticket.id)
      setTickets((items) => [ticket, ...items])
      setSelectedTicket(detail)
      showToast({
        title: tr('Ticket Created'),
        message: tr('Your support request was submitted.'),
        type: 'success',
      })
      setSubject('')
      setMessage('')
    } catch {
      showToast({ title: tr('Ticket could not be created'), message: tr('Please retry your support request.'), type: 'error' })
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleReply = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!selectedTicket || !reply.trim()) return
    setIsReplying(true)
    try {
      await supportApi.replyTicket(selectedTicket.id, reply.trim())
      setSelectedTicket(await supportApi.getTicket(selectedTicket.id))
      setReply('')
    } catch {
      showToast({ title: tr('Reply failed'), message: tr('Your message could not be sent.'), type: 'error' })
    } finally {
      setIsReplying(false)
    }
  }

  return (
    <div className="space-y-8 max-w-2xl mx-auto">
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
          <Headphones className="w-7 h-7" />
        </div>
        <div>
          <h2 className="text-2xl font-black text-white">{tr('Support Center')}</h2>
          <p className="text-xs text-slate-400">
            {tr('Create a ticket below to contact the support team and follow replies.')}
          </p>
        </div>
      </div>

      {/* FAQ Section */}
      <div className="space-y-3">
        <h4 className="text-base font-bold text-white flex items-center gap-2">
          <MessageCircle className="w-4 h-4 text-slate-400" />
          {tr('Frequently Asked Questions')}
        </h4>

        {faqs.map((faq, idx) => (
          <div key={idx} className="bg-dark-card border border-dark-border rounded-2xl overflow-hidden shadow-md">
            <button
              onClick={() => setOpenFaqIdx(openFaqIdx === idx ? null : idx)}
              className="w-full flex items-center justify-between p-4 text-left hover:bg-dark-elevated/40 transition-colors"
            >
              <span className="text-sm font-semibold text-white pr-4">{tr(faq.q)}</span>
              {openFaqIdx === idx ? (
                <ChevronUp className="w-4 h-4 text-slate-400 shrink-0" />
              ) : (
                <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
              )}
            </button>
            {openFaqIdx === idx && (
              <div className="px-4 pb-4 text-xs text-slate-400 leading-relaxed border-t border-dark-border pt-3">
                {tr(faq.a)}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Create Ticket Form */}
      <form
        onSubmit={handleSubmit}
        className="p-6 rounded-2xl bg-dark-card border border-dark-border shadow-xl space-y-4"
      >
        <div className="flex items-center gap-2 mb-1">
          <Plus className="w-4 h-4 text-emerald-400" />
          <h4 className="text-base font-bold text-white">{tr('Open Support Ticket')}</h4>
        </div>

        <Input
          label={tr('Subject')}
          placeholder={tr('Brief summary of your issue')}
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          required
        />

        <div className="space-y-1.5">
          <label className="block text-xs font-semibold text-slate-300">{tr('Category')}</label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full bg-dark-elevated border border-dark-border rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-emerald-500"
          >
            <option value="deposit">{tr('Wallet / Credits')}</option>
            <option value="withdrawal">{tr('Account issue')}</option>
            <option value="gameplay">{tr('Game Disconnection / Round Issue')}</option>
            <option value="account">{tr('Account / Login Problem')}</option>
            <option value="fairness">{tr('Provably Fair Verification')}</option>
            <option value="other">{tr('Other Inquiry')}</option>
          </select>
        </div>

        <div className="space-y-1.5">
          <label className="block text-xs font-semibold text-slate-300">{tr('Message')}</label>
          <textarea
            rows={4}
            required
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={tr('Describe your issue in detail...')}
            className="w-full bg-dark-elevated border border-dark-border rounded-xl p-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 resize-none"
          />
        </div>

        <Button
          type="submit"
          variant="primary"
          className="w-full font-bold"
          isLoading={isSubmitting}
          leftIcon={<Headphones className="w-4 h-4" />}
        >
          Submit Ticket
        </Button>
      </form>
      <section className="space-y-3">
        <h4 className="text-base font-bold text-white">{tr('Your support tickets')}</h4>
        {tickets.length === 0 ? <p className="text-xs text-slate-400">{tr('No tickets yet.')}</p> : tickets.map((ticket) => (
          <button type="button" key={ticket.id} onClick={() => supportApi.getTicket(ticket.id).then(setSelectedTicket).catch(() => showToast({ title: tr('Ticket unavailable'), type: 'error' }))} className="w-full rounded-xl border border-dark-border bg-dark-card p-4 text-left hover:border-emerald-500">
            <span className="block text-sm font-semibold text-white">{ticket.subject}</span><span className="mt-1 block text-xs text-slate-400">{ticket.status} • {ticket.priority}</span>
          </button>
        ))}
      </section>
      {selectedTicket && <section className="rounded-2xl border border-dark-border bg-dark-card p-5 space-y-4">
        <h4 className="font-bold text-white">{selectedTicket.subject}</h4>
        <div className="space-y-3">{selectedTicket.messages.map((item) => <article key={item.id} className="rounded-xl bg-dark-elevated p-3"><p className="text-[10px] uppercase text-slate-400">{item.senderRole === 'user' ? 'You' : 'Support'} • {new Date(item.createdAt).toLocaleString()}</p><p className="mt-1 text-sm text-slate-200">{item.message}</p></article>)}</div>
        {selectedTicket.status !== 'closed' && selectedTicket.status !== 'resolved' && <form onSubmit={handleReply} className="space-y-2"><textarea value={reply} onChange={(event) => setReply(event.target.value)} required rows={3} className="w-full rounded-xl bg-dark-elevated border border-dark-border p-3 text-sm text-white" placeholder={tr('Write a reply…')} /><Button type="submit" isLoading={isReplying} disabled={!reply.trim()}>{tr('Send reply')}</Button></form>}
      </section>}
    </div>
  )
}
