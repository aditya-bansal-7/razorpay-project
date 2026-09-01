import type { ActivityRecord, CollectionReminder, Customer, LedgerEntry, PaymentLinkDraft } from './types'

export interface CustomerService { list(): Customer[]; get(id: string): Customer | undefined; create(input: Pick<Customer, 'name' | 'phone' | 'email' | 'address'>): Customer }
export interface LedgerService { list(customerId?: string): LedgerEntry[]; create(input: Pick<LedgerEntry, 'customerId' | 'type' | 'amount' | 'description'>): LedgerEntry }
export interface ActivityService { list(): ActivityRecord[] }
export interface PaymentLinkService { createPaymentLink(customerId: string, amount: number): Promise<{ url: string }> }
export interface WebhookHandler { handle(payload: unknown): Promise<void> }
export interface CollectionEngine { recommend(customerId: string): Promise<string> }
export interface PaymentLinkDraftService { create(customerId: string, amount: number): PaymentLinkDraft }
export interface ReminderService { create(input: Pick<CollectionReminder, 'customerId' | 'paymentLinkId' | 'message'>): CollectionReminder }
export interface RazorpayPaymentLinkService extends PaymentLinkDraftService {}
export interface RazorpayWebhookHandler extends WebhookHandler {}
export interface FastApiService extends FastApiClient {}
export interface AiCollectionEngine extends CollectionEngine {}
export interface FastApiClient { health(): Promise<boolean> }

export const futureServiceContracts = ['Razorpay Payment Link service', 'Razorpay webhook handler', 'FastAPI service', 'AI collection engine'] as const
