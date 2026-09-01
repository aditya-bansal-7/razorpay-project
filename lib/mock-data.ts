import type { ActivityRecord, Customer, LedgerEntry, Merchant } from './types'

export const merchant: Merchant = { id: 'merchant-001', name: 'KiranaKart Supplies', email: 'owner@kir anakart.in'.replace(' ', ''), createdAt: new Date('2024-01-01') }

const customerSeed = [
  ['customer-001', 'Ramesh General Store', '9876543210', 'overdue'],
  ['customer-002', 'Anita Traders', '9812345678', 'active'],
  ['customer-003', 'Sharma Hardware', '9898989898', 'active'],
  ['customer-004', 'Mehta Provisions', '9765432109', 'active'],
  ['customer-005', 'Lakshmi Cafe', '9123456780', 'settled'],
  ['customer-006', 'Patel Electricals', '9988776655', 'active'],
  ['customer-007', 'Gupta Textiles', '9090909090', 'overdue'],
  ['customer-008', 'Newtown Medicals', '9000011111', 'active'],
] as const
export const customers: Customer[] = customerSeed.map(([id, name, phone, status], index) => ({ id, merchantId: merchant.id, name, phone, status, createdAt: new Date(`2025-0${(index % 8) + 1}-05`), updatedAt: new Date('2026-08-30') }))

export const ledgerEntries: LedgerEntry[] = [
  { id: 'ledger-001', merchantId: merchant.id, customerId: 'customer-001', type: 'credit', amount: 18000, currency: 'INR', description: 'Monthly stock supplies', createdAt: new Date('2026-05-10'), updatedAt: new Date('2026-05-10') },
  { id: 'ledger-002', merchantId: merchant.id, customerId: 'customer-001', type: 'credit', amount: 12500, currency: 'INR', description: 'Additional grocery stock', createdAt: new Date('2026-06-08'), updatedAt: new Date('2026-06-08') },
  { id: 'ledger-003', merchantId: merchant.id, customerId: 'customer-001', type: 'payment', amount: 10000, currency: 'INR', description: 'UPI payment', createdAt: new Date('2026-06-22'), updatedAt: new Date('2026-06-22') },
  { id: 'ledger-004', merchantId: merchant.id, customerId: 'customer-001', type: 'payment', amount: 5000, currency: 'INR', description: 'Cash payment', createdAt: new Date('2026-07-14'), updatedAt: new Date('2026-07-14') },
  { id: 'ledger-005', merchantId: merchant.id, customerId: 'customer-001', type: 'credit', amount: 7500, currency: 'INR', description: 'Festival inventory', createdAt: new Date('2026-08-02'), updatedAt: new Date('2026-08-02') },
  { id: 'ledger-006', merchantId: merchant.id, customerId: 'customer-002', type: 'credit', amount: 22000, currency: 'INR', description: 'Wholesale order', createdAt: new Date('2026-07-18'), updatedAt: new Date('2026-07-18') },
  { id: 'ledger-007', merchantId: merchant.id, customerId: 'customer-002', type: 'payment', amount: 22000, currency: 'INR', description: 'Full settlement', createdAt: new Date('2026-08-05'), updatedAt: new Date('2026-08-05') },
  { id: 'ledger-008', merchantId: merchant.id, customerId: 'customer-003', type: 'credit', amount: 34000, currency: 'INR', description: 'Hardware materials', createdAt: new Date('2026-08-12'), updatedAt: new Date('2026-08-12') },
  { id: 'ledger-009', merchantId: merchant.id, customerId: 'customer-004', type: 'credit', amount: 9800, currency: 'INR', description: 'Pantry restock', createdAt: new Date('2026-08-20'), updatedAt: new Date('2026-08-20') },
  { id: 'ledger-010', merchantId: merchant.id, customerId: 'customer-004', type: 'payment', amount: 3000, currency: 'INR', description: 'Cash payment', createdAt: new Date('2026-08-27'), updatedAt: new Date('2026-08-27') },
  { id: 'ledger-011', merchantId: merchant.id, customerId: 'customer-006', type: 'credit', amount: 15750, currency: 'INR', description: 'Electrical stock', createdAt: new Date('2026-08-25'), updatedAt: new Date('2026-08-25') },
  { id: 'ledger-012', merchantId: merchant.id, customerId: 'customer-007', type: 'credit', amount: 27500, currency: 'INR', description: 'Textile order', createdAt: new Date('2026-07-01'), updatedAt: new Date('2026-07-01') },
  { id: 'ledger-013', merchantId: merchant.id, customerId: 'customer-007', type: 'payment', amount: 7500, currency: 'INR', description: 'Partial payment', createdAt: new Date('2026-07-20'), updatedAt: new Date('2026-07-20') },
]
export const activity: ActivityRecord[] = ledgerEntries.slice(0, 8).map((entry, index) => ({ id: `activity-${String(index + 1).padStart(3, '0')}`, merchantId: merchant.id, customerId: entry.customerId, type: entry.type === 'credit' ? 'udhaar_given' : 'payment_recorded', description: `${entry.type === 'credit' ? 'Udhaar added for' : 'Payment received from'} ${customers.find((c) => c.id === entry.customerId)?.name}`, timestamp: entry.createdAt }))
for (let i = 14; i <= 110; i++) { const customer = customers[i % customers.length]; ledgerEntries.push({ id: `ledger-${String(i).padStart(3, '0')}`, merchantId: merchant.id, customerId: customer.id, type: i % 3 === 0 ? 'payment' : 'credit', amount: (i % 7 + 1) * 1250, currency: 'INR', description: i % 3 === 0 ? 'Routine payment' : 'Stock order', createdAt: new Date(2026, 3 + (i % 5), (i % 26) + 1), updatedAt: new Date(2026, 3 + (i % 5), (i % 26) + 1) }) }
export const seed = { merchant, customers, ledgerEntries, activity }

export function balanceFor(customerId: string, entries: LedgerEntry[] = ledgerEntries) { return entries.filter((e) => e.customerId === customerId).reduce((total, e) => total + (e.type === 'payment' ? -e.amount : e.amount), 0) }
export function totals(entries: LedgerEntry[] = ledgerEntries) { const outstanding = entries.reduce((sum, e) => sum + (e.type === 'payment' ? -e.amount : e.amount), 0); return { outstanding, collected: entries.filter((e) => e.type === 'payment').reduce((s, e) => s + e.amount, 0) } }

export const futureIntegrations = { razorpayPaymentLink: 'Razorpay Payment Link service', razorpayWebhook: 'Razorpay webhook handler', fastApi: 'FastAPI service', aiCollectionEngine: 'AI collection engine' } as const

export function cloneSeed() { return { merchant: { ...merchant }, customers: customers.map((c) => ({ ...c })), ledgerEntries: ledgerEntries.map((e) => ({ ...e })), activity: activity.map((a) => ({ ...a })) } }

export function formatINR(amount: number) { return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(amount) }
export function formatDate(date: Date) { return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) }
export function initials(name: string) { return name.split(' ').map((part) => part[0]).slice(0, 2).join('').toUpperCase() }
export function relativeTime(date: Date) { const days = Math.max(0, Math.round((Date.now() - date.getTime()) / 86400000)); return days === 0 ? 'Today' : `${days}d ago` }
export function getCustomer(customerId: string, list = customers) { return list.find((c) => c.id === customerId) }
export function getEntries(customerId: string, entries = ledgerEntries) { return entries.filter((e) => e.customerId === customerId).sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime()) }
export function getBalance(customerId: string, entries = ledgerEntries) { const own = getEntries(customerId, entries); return { totalCredit: own.filter((e) => e.type === 'credit').reduce((s, e) => s + e.amount, 0), totalPayment: own.filter((e) => e.type === 'payment').reduce((s, e) => s + e.amount, 0), totalAdjustment: own.filter((e) => e.type === 'adjustment').reduce((s, e) => s + e.amount, 0), outstandingBalance: balanceFor(customerId, entries), lastUpdated: own[0]?.updatedAt ?? new Date() } }
