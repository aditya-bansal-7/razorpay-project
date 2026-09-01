import { cloneSeed } from './mock-data'
import type { Customer, LedgerEntry } from './types'
import type { ActivityService, CustomerService, LedgerService } from './services'

const data = cloneSeed()
export const mockCustomerService: CustomerService = { list: () => data.customers, get: (id) => data.customers.find((c) => c.id === id), create: (input) => { const now = new Date(); const customer = { ...input, id: `customer-${crypto.randomUUID()}`, merchantId: data.merchant.id, status: 'active' as const, createdAt: now, updatedAt: now }; data.customers.unshift(customer); return customer } }
export const mockLedgerService: LedgerService = { list: (customerId) => customerId ? data.ledgerEntries.filter((e) => e.customerId === customerId) : data.ledgerEntries, create: (input) => { const now = new Date(); const entry: LedgerEntry = { ...input, id: `ledger-${crypto.randomUUID()}`, merchantId: data.merchant.id, currency: 'INR', createdAt: now, updatedAt: now }; data.ledgerEntries.unshift(entry); return entry } }
export const mockActivityService: ActivityService = { list: () => data.activity }
