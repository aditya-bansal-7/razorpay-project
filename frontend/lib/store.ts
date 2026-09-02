'use client'

import { create } from 'zustand'
import { api, toCustomerModel, toLedgerModel } from './api'
import type { ActivityRecord, CollectionReminder, Customer, LedgerEntry, PaymentLinkDraft } from './types'

type CustomerInput = Pick<Customer, 'name' | 'phone' | 'email' | 'address'>
type LedgerInput = Pick<LedgerEntry, 'customerId' | 'type' | 'amount' | 'description'>

type State = {
  customers: Customer[]
  ledgerEntries: LedgerEntry[]
  activity: ActivityRecord[]
  paymentLinks: PaymentLinkDraft[]
  reminders: CollectionReminder[]
  loading: boolean
  error: string | null
  hydrate: () => Promise<void>
  refreshCustomers: () => Promise<void>
  refreshLedger: () => Promise<void>
  addCustomer: (input: CustomerInput) => Promise<Customer | { error: string }>
  addLedgerEntry: (input: LedgerInput) => Promise<{ entry?: LedgerEntry; error?: string }>
  createPaymentLink: (customerId: string, amount: number) => PaymentLinkDraft | { error: string }
  createReminder: (input: { customerId: string; paymentLinkId: string; message: string }) => CollectionReminder
  balance: (customerId: string) => {
    totalCredit: number
    totalPayment: number
    totalAdjustment: number
    outstandingBalance: number
    lastUpdated: Date
  }
}

export const useUdhaarStore = create<State>((set, get) => ({
  customers: [],
  ledgerEntries: [],
  activity: [],
  paymentLinks: [],
  reminders: [],
  loading: false,
  error: null,
  hydrate: async () => {
    set({ loading: true, error: null })

    const [customersResponse, ledgerResponse] = await Promise.all([
      api.listCustomers(),
      api.listLedger(),
    ])

    if (customersResponse.error) {
      set({ error: customersResponse.error, loading: false })
      return
    }

    const customers = (customersResponse.data ?? []).map(toCustomerModel)
    const ledgerEntries = (ledgerResponse.data ?? []).map(toLedgerModel)

    set({
      customers,
      ledgerEntries,
      activity: ledgerEntries.slice(0, 8).map((entry) => ({
        id: `activity-${entry.id}`,
        merchantId: entry.merchantId,
        customerId: entry.customerId,
        type: entry.type === 'credit' ? 'udhaar_given' : entry.type === 'payment' ? 'payment_recorded' : 'adjustment',
        description: `${entry.type === 'credit' ? 'Udhaar added for' : entry.type === 'payment' ? 'Payment received from' : 'Adjustment recorded for'} ${customers.find((c) => c.id === entry.customerId)?.name ?? 'customer'}`,
        timestamp: entry.createdAt,
      })),
      loading: false,
    })
  },
  refreshCustomers: async () => {
    const response = await api.listCustomers()
    if (response.error) {
      set({ error: response.error })
      return
    }
    set({ customers: (response.data ?? []).map(toCustomerModel) })
  },
  refreshLedger: async () => {
    const response = await api.listLedger()
    if (response.error) {
      set({ error: response.error })
      return
    }
    const ledgerEntries = (response.data ?? []).map(toLedgerModel)
    set({
      ledgerEntries,
      activity: ledgerEntries.slice(0, 8).map((entry) => ({
        id: `activity-${entry.id}`,
        merchantId: entry.merchantId,
        customerId: entry.customerId,
        type: entry.type === 'credit' ? 'udhaar_given' : entry.type === 'payment' ? 'payment_recorded' : 'adjustment',
        description: `${entry.type === 'credit' ? 'Udhaar added for' : entry.type === 'payment' ? 'Payment received from' : 'Adjustment recorded for'} ${get().customers.find((c) => c.id === entry.customerId)?.name ?? 'customer'}`,
        timestamp: entry.createdAt,
      })),
    })
  },
  addCustomer: async (input) => {
    const response = await api.createCustomer(input)
    if (response.error) return { error: response.error }

    const customer = toCustomerModel(response.data as any)
    set((state) => ({
      customers: [customer, ...state.customers],
      activity: [{
        id: `activity-${customer.id}`,
        merchantId: customer.merchantId,
        customerId: customer.id,
        type: 'customer_created',
        description: `New customer added: ${customer.name}`,
        timestamp: customer.createdAt,
      }, ...state.activity],
    }))
    return customer
  },
  addLedgerEntry: async (input) => {
    const balance = get().balance(input.customerId)
    if (input.type === 'payment' && input.amount > balance.outstandingBalance) {
      return { error: 'Payment cannot be greater than the outstanding balance.' }
    }

    const response = await api.createLedgerEntry(input.customerId, {
      type: input.type,
      amount: input.amount,
      description: input.description,
    })

    if (response.error) return { error: response.error }

    const entry = toLedgerModel(response.data as any)
    set((state) => ({
      ledgerEntries: [entry, ...state.ledgerEntries],
      activity: [{
        id: `activity-${entry.id}`,
        merchantId: entry.merchantId,
        customerId: entry.customerId,
        type: entry.type === 'credit' ? 'udhaar_given' : entry.type === 'payment' ? 'payment_recorded' : 'adjustment',
        description: `${entry.type === 'credit' ? 'Udhaar added for' : entry.type === 'payment' ? 'Payment received from' : 'Adjustment recorded for'} ${state.customers.find((c) => c.id === entry.customerId)?.name ?? 'customer'}`,
        timestamp: entry.createdAt,
      }, ...state.activity],
    }))
    return { entry }
  },
  createPaymentLink: (customerId, amount) => {
    const balance = get().balance(customerId).outstandingBalance
    if (!Number.isFinite(amount) || amount <= 0 || amount > balance) {
      return { error: 'Enter an amount up to the current outstanding balance.' }
    }

    const link: PaymentLinkDraft = {
      id: `payment-link-${crypto.randomUUID()}`,
      merchantId: 'merchant-001',
      customerId,
      amount,
      url: `https://rzp.io/i/udhaar-${customerId.slice(-3)}-${amount}`,
      provider: 'mock',
      status: 'draft',
      createdAt: new Date(),
    }

    set((state) => ({ paymentLinks: [link, ...state.paymentLinks] }))
    return link
  },
  createReminder: (input) => {
    const reminder: CollectionReminder = {
      ...input,
      id: `activity-${crypto.randomUUID()}`,
      merchantId: 'merchant-001',
      channel: 'whatsapp',
      status: 'ready',
      createdAt: new Date(),
    }

    set((state) => ({ reminders: [reminder, ...state.reminders] }))
    return reminder
  },
  balance: (customerId) => {
    const own = get().ledgerEntries.filter((entry) => entry.customerId === customerId).sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime())
    return {
      totalCredit: own.filter((entry) => entry.type === 'credit').reduce((sum, entry) => sum + entry.amount, 0),
      totalPayment: own.filter((entry) => entry.type === 'payment').reduce((sum, entry) => sum + entry.amount, 0),
      totalAdjustment: own.filter((entry) => entry.type === 'adjustment').reduce((sum, entry) => sum + entry.amount, 0),
      outstandingBalance: own.reduce((sum, entry) => sum + (entry.type === 'payment' ? -entry.amount : entry.amount), 0),
      lastUpdated: own[0]?.updatedAt ?? new Date(),
    }
  },
}))
