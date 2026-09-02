const DEFAULT_API_URL = 'http://localhost:5000/api'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL

function normalizeDate(value?: string | Date | null): Date {
  if (!value) return new Date()
  return value instanceof Date ? value : new Date(value)
}

export type ApiResponse<T> = {
  data?: T
  error?: string
  status: number
}

async function request<T>(path: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers ?? {}),
      },
    })

    const contentType = response.headers.get('content-type') ?? ''
    const body = contentType.includes('application/json') ? await response.json() : await response.text()

    if (!response.ok) {
      const message = typeof body === 'string' ? body : body?.error ?? 'Request failed'
      return { error: message, status: response.status }
    }

    return { data: (body && body.data !== undefined ? body.data : body) as T, status: response.status }
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Network error',
      status: 500,
    }
  }
}

export type CustomerApi = {
  id: string
  merchantId: string
  name: string
  phone: string
  email?: string
  address?: string
  status: 'active' | 'inactive' | 'overdue' | 'settled'
  createdAt: string
  updatedAt: string
}

export type LedgerApi = {
  id: string
  merchantId: string
  customerId: string
  type: 'credit' | 'payment' | 'adjustment'
  amount: number
  currency: string
  description: string
  createdAt: string
  updatedAt: string
}

export type BalanceApi = {
  customerId: string
  total_credit: number
  total_payment: number
  total_adjustment: number
  outstanding_balance: number
  customer_status?: 'active' | 'overdue' | 'settled'
  days_overdue?: number
  last_updated: string
}

export type DashboardMetricsApi = {
  totalCustomers: number
  totalOutstandingBalance: number
  totalCollected: number
  averageBalance: number
  overdueAmount: number
  overdueCustomerCount: number
  lastUpdated: string
}

export const api = {
  listCustomers: () => request<CustomerApi[]>('/customers'),
  getCustomer: (customerId: string) => request<CustomerApi>(`/customers/${customerId}`),
  createCustomer: (payload: { name: string; phone: string; email?: string; address?: string }) =>
    request<CustomerApi>('/customers', { method: 'POST', body: JSON.stringify(payload) }),
  updateCustomer: (customerId: string, payload: Partial<{ name: string; phone: string; email?: string; address?: string; status: string }>) =>
    request<CustomerApi>(`/customers/${customerId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteCustomer: (customerId: string) => request<{ success: boolean }>(`/customers/${customerId}`, { method: 'DELETE' }),
  listCustomerLedger: (customerId: string) => request<LedgerApi[]>(`/customers/${customerId}/ledger`),
  createLedgerEntry: (customerId: string, payload: { type: 'credit' | 'payment' | 'adjustment'; amount: number; description?: string; currency?: string }) =>
    request<LedgerApi>(`/customers/${customerId}/ledger`, { method: 'POST', body: JSON.stringify(payload) }),
  getBalance: (customerId: string) => request<BalanceApi>(`/customers/${customerId}/balance`),
  listLedger: () => request<LedgerApi[]>('/ledger'),
  listDashboard: () => request<DashboardMetricsApi>('/dashboard'),
}

export function toCustomerModel(data: CustomerApi) {
  return {
    id: data.id,
    merchantId: data.merchantId,
    name: data.name,
    phone: data.phone,
    email: data.email,
    address: data.address,
    status: data.status,
    createdAt: normalizeDate(data.createdAt),
    updatedAt: normalizeDate(data.updatedAt),
  }
}

export function toLedgerModel(data: LedgerApi) {
  return {
    id: data.id,
    merchantId: data.merchantId,
    customerId: data.customerId,
    type: data.type,
    amount: Number(data.amount),
    currency: data.currency,
    description: data.description,
    createdAt: normalizeDate(data.createdAt),
    updatedAt: normalizeDate(data.updatedAt),
  }
}
