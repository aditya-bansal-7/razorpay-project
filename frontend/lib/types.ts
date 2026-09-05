/**
 * UdhaarAI M1 Domain Models
 *
 * All entities use stable UUIDs. Balances are always derived from ledger entries.
 * No independent balance fields are maintained to prevent inconsistency.
 */

export interface Merchant {
  id: string
  name: string
  email: string
  createdAt: Date
}

export interface Customer {
  id: string
  merchantId: string
  name: string
  phone: string
  email?: string
  address?: string
  status: 'active' | 'inactive' | 'overdue' | 'settled'
  createdAt: Date
  updatedAt: Date
}

export interface LedgerEntry {
  id: string
  merchantId: string
  customerId: string
  type: 'credit' | 'payment' | 'adjustment'
  amount: number
  currency: string
  description: string
  transactionDate?: Date
  dueDate?: Date
  createdAt: Date
  updatedAt: Date
}

export interface ActivityRecord {
  id: string
  merchantId: string
  customerId?: string
  type: 'customer_created' | 'udhaar_given' | 'payment_recorded' | 'adjustment' | 'status_changed'
  description: string
  timestamp: Date
}

export interface CollectionQueueItem {
  id: string
  merchantId: string
  customerId: string
  customerName: string
  outstandingBalance: number
  priority: 'high' | 'medium' | 'low'
  daysOverdue: number
  recommendedAction: string
  createdAt: Date
}

export interface PaymentLinkDraft {
  id: string
  merchantId: string
  customerId: string
  amount: number
  url: string
  provider: 'razorpay'
  status: 'draft' | 'shared' | 'paid'
  createdAt: Date
}

export interface CollectionReminder {
  id: string
  merchantId: string
  customerId: string
  paymentLinkId: string
  channel: 'whatsapp'
  message: string
  status: 'ready' | 'shared'
  createdAt: Date
}

/**
 * Derived balance calculation from ledger entries:
 * Outstanding Balance = SUM(CREDIT) - SUM(PAYMENT) + SUM(ADJUSTMENT)
 */
export interface CustomerBalance {
  customerId: string
  totalCredit: number
  totalPayment: number
  totalAdjustment: number
  outstandingBalance: number
  lastUpdated: Date
}

export interface DashboardMetrics {
  totalCustomers: number
  totalOutstandingBalance: number
  totalCollected: number
  averageBalance: number
  overdueDays30: number
  lastUpdated: Date
}
