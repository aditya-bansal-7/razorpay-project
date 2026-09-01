import type { ActivityRecord, Customer, LedgerEntry } from './types'

export interface CustomerService { list(): Customer[]; get(id: string): Customer | undefined; create(input: Pick<Customer, 'name' | 'phone' | 'email' | 'address'>): Customer }
export interface LedgerService { list(customerId?: string): LedgerEntry[]; create(input: Pick<LedgerEntry, 'customerId' | 'type' | 'amount' | 'description'>): LedgerEntry }
export interface ActivityService { list(): ActivityRecord[] }
export interface PaymentLinkService { createPaymentLink(customerId: string, amount: number): Promise<{ url: string }> }
export interface WebhookHandler { handle(payload: unknown): Promise<void> }
export interface CollectionEngine { recommend(customerId: string): Promise<string> }
export interface FastApiClient { health(): Promise<boolean> }

export const futureServiceContracts = ['Razorpay Payment Link service', 'Razorpay webhook handler', 'FastAPI service', 'AI collection engine'] as const
