"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  Bell,
  ChevronRight,
  CircleDollarSign,
  LayoutDashboard,
  Menu,
  Plus,
  Search,
  Settings,
  Users,
  X,
} from "lucide-react";
import { useUdhaarStore } from "@/lib/store";
import {
  formatDate,
  formatINR,
  getBalance,
  getEntries,
  initials,
  relativeTime,
} from "@/lib/mock-data";
import type { Customer, LedgerEntry } from "@/lib/types";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/customers", label: "Customers", icon: Users },
  { href: "/ledger", label: "Ledger", icon: CircleDollarSign },
  { href: "/settings", label: "Settings", icon: Settings },
];
function money(n: number) {
  return formatINR(n).replace("₹", "₹ ");
}
function Status({ value }: { value: Customer["status"] }) {
  return (
    <span className={`status status-${value}`}>
      {value === "overdue"
        ? "Overdue"
        : value === "settled"
          ? "Settled"
          : "Active"}
    </span>
  );
}
function TypeBadge({ type }: { type: LedgerEntry["type"] }) {
  return (
    <span className={`type type-${type}`}>
      {type === "credit"
        ? "Udhaar"
        : type === "payment"
          ? "Payment"
          : "Adjustment"}
    </span>
  );
}
function Layout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  return (
    <div className="app-shell">
      <aside className={open ? "sidebar sidebar-open" : "sidebar"}>
        <div className="brand">
          <div className="brand-mark">U</div>
          <span>
            Udhaar<span>AI</span>
          </span>
          <button
            className="close-mobile"
            onClick={() => setOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>
        <nav>
          {nav.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setOpen(false)}
              className={
                pathname.startsWith(href) ? "nav-link active" : "nav-link"
              }
            >
              <Icon size={18} />
              {label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="merchant-avatar">KK</div>
          <div>
            <strong>KiranaKart</strong>
            <small>Merchant account</small>
          </div>
          <ChevronRight size={16} />
        </div>
      </aside>
      <div className="main-wrap">
        <header className="topbar">
          <button
            className="mobile-menu"
            onClick={() => setOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={20} />
          </button>
          <div>
            <span className="eyebrow">Merchant workspace</span>
            <h1>
              {pathname.includes("customers/")
                ? "Customer detail"
                : pathname === "/customers"
                  ? "Customers"
                  : pathname === "/ledger"
                    ? "Ledger"
                    : pathname === "/settings"
                      ? "Settings"
                      : "Good morning, KiranaKart"}
            </h1>
          </div>
          <div className="top-actions">
            <button className="icon-btn" aria-label="Notifications">
              <Bell size={18} />
              <i />
            </button>
            <div className="top-avatar">KK</div>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
function AddCustomer({ onClose }: { onClose: () => void }) {
  const add = useUdhaarStore((s) => s.addCustomer);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState("");
  return (
    <div className="modal-backdrop">
      <div className="modal">
        <div className="modal-head">
          <div>
            <span className="eyebrow">Customer record</span>
            <h2>Add customer</h2>
          </div>
          <button className="icon-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <label>
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Ramesh General Store"
          />
        </label>
        <label>
          Phone number
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="10-digit mobile number"
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button
          className="primary-btn"
          onClick={async () => {
            if (!name || phone.length < 10)
              return setError("Enter a name and valid phone number.");
            const result = await add({ name, phone });
            if ("error" in result) return setError(result.error);
            onClose();
          }}
        >
          Add customer <Plus size={16} />
        </button>
      </div>
    </div>
  );
}
function AddLedger({
  customerId,
  onClose,
}: {
  customerId?: string;
  onClose: () => void;
}) {
  const customers = useUdhaarStore((s) => s.customers);
  const addCustomer = useUdhaarStore((s) => s.addCustomer);
  const add = useUdhaarStore((s) => s.addLedgerEntry);
  const [cid, setCid] = useState(customerId ?? customers[0]?.id ?? "");
  const [search, setSearch] = useState("");
  const [newCustomer, setNewCustomer] = useState(false);
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [type, setType] = useState<"credit" | "payment">("credit");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [returnInDays, setReturnInDays] = useState("30");
  const [error, setError] = useState("");
  const filteredCustomers = customers.filter(
    (customer) =>
      customer.name.toLowerCase().includes(search.toLowerCase()) ||
      customer.phone.includes(search),
  );
  return (
    <div className="modal-backdrop">
      <div className="modal">
        <div className="modal-head">
          <div>
            <span className="eyebrow">Ledger entry</span>
            <h2>{type === "credit" ? "Add udhaar" : "Record payment"}</h2>
          </div>
          <button className="icon-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        {customerId ? (
          <label>
            Customer
            <input value={customers.find((customer) => customer.id === customerId)?.name ?? "Selected customer"} readOnly />
          </label>
        ) : !newCustomer ? (
          <>
            <label>
              Search customer
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name or phone"
              />
            </label>
            <label>
              Customer
              <select value={cid} onChange={(e) => setCid(e.target.value)}>
                {filteredCustomers.length === 0 && <option value="">No matching customer</option>}
                {filteredCustomers.map((c) => (
                  <option value={c.id} key={c.id}>
                    {c.name} · {c.phone}
                  </option>
                ))}
              </select>
            </label>
            <button className="text-link-btn" type="button" onClick={() => setNewCustomer(true)}>
              <Plus size={14} /> New customer
            </button>
          </>
        ) : (
          <>
            <div className="panel-head">
              <div>
                <span className="eyebrow">New customer</span>
                <h3>Create customer and udhaar together</h3>
              </div>
              <button className="text-link-btn" type="button" onClick={() => setNewCustomer(false)}>Choose existing</button>
            </div>
            <label>
              Name
              <input value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="Customer name" />
            </label>
            <label>
              Phone number
              <input value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} placeholder="10-digit mobile number" />
            </label>
          </>
        )}
        <div className="segmented">
          <button
            className={type === "credit" ? "selected" : ""}
            onClick={() => setType("credit")}
          >
            Udhaar given
          </button>
          <button
            className={type === "payment" ? "selected" : ""}
            onClick={() => setType("payment")}
          >
            Payment received
          </button>
        </div>
        <label>
          Amount
          <input
            type="number"
            min="1"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0"
          />
        </label>
        {type === "credit" && (
          <label>
            Return in (days)
            <input
              type="number"
              min="1"
              step="1"
              value={returnInDays}
              onChange={(e) => setReturnInDays(e.target.value)}
              placeholder="30"
            />
          </label>
        )}
        <label>
          Description
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional note"
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button
          className="primary-btn"
          onClick={async () => {
            let selectedCustomerId = cid;
            if (newCustomer) {
              if (!customerName.trim() || customerPhone.length < 10) {
                return setError("Enter a name and valid phone number.");
              }
              const customerResult = await addCustomer({ name: customerName.trim(), phone: customerPhone });
              if ("error" in customerResult) return setError(customerResult.error);
              selectedCustomerId = customerResult.id;
            }
            if (!selectedCustomerId) return setError("Select or create a customer.");
            const days = Number(returnInDays);
            if (type === "credit" && (!Number.isInteger(days) || days < 1)) {
              return setError("Enter a return period of at least 1 day.");
            }
            const dueDate = new Date();
            dueDate.setDate(dueDate.getDate() + (type === "credit" ? days : 0));
            const result = await add({
              customerId: selectedCustomerId,
              type,
              amount: Number(amount),
              description:
                description ||
                (type === "credit" ? "Udhaar added" : "Payment received"),
              dueDate: type === "credit" ? dueDate.toISOString() : undefined,
            });
            if ("error" in result) return setError(result.error);
            onClose();
          }}
        >
          {type === "credit" ? "Add udhaar" : "Record payment"}{" "}
          <ArrowUpRight size={16} />
        </button>
      </div>
    </div>
  );
}
function Overview() {
  const customers = useUdhaarStore((s) => s.customers);
  const entries = useUdhaarStore((s) => s.ledgerEntries);
  const activities = useUdhaarStore((s) => s.activity);
  const [modal, setModal] = useState<"customer" | "ledger" | null>(null);
  const totals = useMemo(() => {
    const outstanding = customers.reduce(
      (s, c) => s + useUdhaarStore.getState().balance(c.id).outstandingBalance,
      0,
    );
    const collected = entries
      .filter((e) => e.type === "payment")
      .reduce((s, e) => s + e.amount, 0);
    return { outstanding, collected };
  }, [customers, entries]);
  const queue = customers
    .map((c) => ({
      c,
      balance: useUdhaarStore.getState().balance(c.id).outstandingBalance,
    }))
    .filter((x) => x.balance > 0)
    .sort((a, b) => b.balance - a.balance)
    .slice(0, 4);
  return (
    <>
      <section className="welcome-row">
        <div>
          <span className="eyebrow">Tuesday, 1 September 2026</span>
          <h2>Here&apos;s your business at a glance.</h2>
        </div>
        <div className="action-row">
          <button
            className="secondary-btn"
            onClick={() => setModal("customer")}
          >
            <Users size={16} /> Add customer
          </button>
          <button className="primary-btn" onClick={() => setModal("ledger")}>
            <Plus size={16} /> Add udhaar
          </button>
        </div>
      </section>
      <section className="metric-grid">
        <div className="metric-card accent">
          <div className="metric-icon">
            <ArrowUpRight size={18} />
          </div>
          <span>Total outstanding</span>
          <strong>{money(totals.outstanding)}</strong>
          <small>Across {customers.length} customers</small>
        </div>
        <div className="metric-card">
          <div className="metric-icon green">
            <ArrowDownLeft size={18} />
          </div>
          <span>Collected this month</span>
          <strong>{money(totals.collected)}</strong>
          <small className="positive">+12.4% from last month</small>
        </div>
        <div className="metric-card">
          <div className="metric-icon amber">
            <Users size={18} />
          </div>
          <span>Active customers</span>
          <strong>
            {
              customers.filter(
                (c) => c.status === "active" || c.status === "overdue",
              ).length
            }
          </strong>
          <small>
            {customers.filter((c) => c.status === "overdue").length} need
            attention
          </small>
        </div>
        <div className="metric-card">
          <div className="metric-icon slate">
            <Activity size={18} />
          </div>
          <span>Average balance</span>
          <strong>{money(totals.outstanding / customers.length)}</strong>
          <small>Per customer</small>
        </div>
      </section>
      <section className="content-grid">
        <div className="panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">Prioritised follow-up</span>
              <h3>Collection queue</h3>
            </div>
            <Link href="/customers" className="text-link">
              View all <ChevronRight size={15} />
            </Link>
          </div>
          <div className="queue-list">
            {queue.map(({ c, balance }) => (
              <Link
                href={`/customers/${c.id}`}
                className="queue-item"
                key={c.id}
              >
                <div className="avatar">{initials(c.name)}</div>
                <div className="queue-name">
                  <strong>{c.name}</strong>
                  <small>
                    {c.status === "overdue"
                      ? "Overdue · Follow up today"
                      : "Recommended · Send reminder"}
                  </small>
                </div>
                <div className="queue-amount">
                  <strong>{money(balance)}</strong>
                  <ChevronRight size={16} />
                </div>
              </Link>
            ))}
          </div>
        </div>
        <div className="panel activity-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">Live updates</span>
              <h3>Recent activity</h3>
            </div>
            <Activity size={18} className="muted" />
          </div>
          <div className="activity-list">
            {activities.slice(0, 6).map((a) => (
              <div className="activity-item" key={a.id}>
                <div className="activity-dot" />
                <div>
                  <p>{a.description}</p>
                  <small>{relativeTime(a.timestamp)}</small>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
      {modal === "customer" && <AddCustomer onClose={() => setModal(null)} />}
      {modal === "ledger" && <AddLedger onClose={() => setModal(null)} />}
    </>
  );
}
function CustomersPage() {
  const customers = useUdhaarStore((s) => s.customers);
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(false);
  const filtered = customers.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.phone.includes(search),
  );
  return (
    <>
      <section className="page-intro">
        <div>
          <span className="eyebrow">Relationship book</span>
          <h2>Customers</h2>
          <p>Every customer, every outstanding rupee, in one place.</p>
        </div>
        <button className="primary-btn" onClick={() => setModal(true)}>
          <Plus size={16} /> Add customer
        </button>
      </section>
      <div className="toolbar">
        <div className="search-box">
          <Search size={17} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search customers"
          />
        </div>
        <span className="result-count">{filtered.length} customers</span>
      </div>
      <div className="table-panel">
        <table>
          <thead>
            <tr>
              <th>Customer</th>
              <th>Status</th>
              <th>Outstanding</th>
              <th>Last activity</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filtered.map((c) => {
              const balance = useUdhaarStore.getState().balance(c.id);
              const last = getEntries(
                c.id,
                useUdhaarStore.getState().ledgerEntries,
              )[0];
              return (
                <tr key={c.id}>
                  <td>
                    <Link href={`/customers/${c.id}`} className="customer-cell">
                      <span className="avatar small">{initials(c.name)}</span>
                      <span>
                        <strong>{c.name}</strong>
                        <small>{c.phone}</small>
                      </span>
                    </Link>
                  </td>
                  <td>
                    <Status value={c.status} />
                  </td>
                  <td className="amount-cell">
                    {money(balance.outstandingBalance)}
                  </td>
                  <td className="muted">
                    {last ? formatDate(last.createdAt) : "—"}
                  </td>
                  <td>
                    <Link href={`/customers/${c.id}`} className="row-link">
                      <ChevronRight size={17} />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {modal && <AddCustomer onClose={() => setModal(false)} />}
    </>
  );
}
function LedgerPage() {
  const entries = useUdhaarStore((s) => s.ledgerEntries);
  const customers = useUdhaarStore((s) => s.customers);
  const [modal, setModal] = useState(false);
  return (
    <>
      <section className="page-intro">
        <div>
          <span className="eyebrow">Source of truth</span>
          <h2>Ledger</h2>
          <p>All credits, payments, and adjustments across your book.</p>
        </div>
        <button className="primary-btn" onClick={() => setModal(true)}>
          <Plus size={16} /> Add entry
        </button>
      </section>
      <div className="table-panel">
        <table>
          <thead>
            <tr>
              <th>Transaction</th>
              <th>Customer</th>
              <th>Type</th>
              <th>Description</th>
              <th>Due date</th>
              <th className="right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {entries.slice(0, 40).map((e) => (
              <tr key={e.id}>
                <td className="muted">
                  {formatDate(e.transactionDate ?? e.createdAt)}
                </td>
                <td>
                  <strong>
                    {customers.find((c) => c.id === e.customerId)?.name}
                  </strong>
                </td>
                <td>
                  <TypeBadge type={e.type} />
                </td>
                <td className="muted">{e.description}</td>
                <td className="muted">
                  {e.dueDate ? formatDate(e.dueDate) : "—"}
                </td>
                <td
                  className={
                    e.type === "payment"
                      ? "right amount-positive"
                      : "right amount-cell"
                  }
                >
                  {e.type === "payment" ? "−" : "+"}
                  {money(e.amount)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {modal && <AddLedger onClose={() => setModal(false)} />}
    </>
  );
}
function PaymentReminder({
  customer,
  onClose,
}: {
  customer: Customer;
  onClose: () => void;
}) {
  const entries = useUdhaarStore((s) => s.ledgerEntries);
  const balance = getBalance(customer.id, entries);
  const createLink = useUdhaarStore((s) => s.createPaymentLink);
  const createReminder = useUdhaarStore((s) => s.createReminder);
  const [amount, setAmount] = useState(String(balance.outstandingBalance));
  const [link, setLink] = useState("");
  const [error, setError] = useState("");
  const [shared, setShared] = useState(false);
  const message = `Hi ${customer.name}, a payment of ${money(Number(amount) || 0)} is due to KiranaKart. Please pay securely here: ${link}`;
  const generate = async () => {
    const result = await createLink(customer.id, Number(amount));
    if ("error" in result) return setError(result.error);
    setLink(result.url);
    setError("");
  };
  const share = () => {
    if (!link) return setError("Create the payment link first.");
    createReminder({ customerId: customer.id, paymentLinkId: link, message });
    setShared(true);
    window.open(
      `https://wa.me/${customer.phone}?text=${encodeURIComponent(message)}`,
      "_blank",
      "noopener,noreferrer",
    );
  };
  return (
    <div className="modal-backdrop">
      <div className="modal">
        <div className="modal-head">
          <div>
            <span className="eyebrow">Collection reminder</span>
            <h2>Send payment link</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <p className="modal-note">
          Generate a secure Razorpay link for this customer.
        </p>
        <label>
          Amount
          <input
            type="number"
            min="1"
            max={balance.outstandingBalance}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </label>
        {link && (
          <div className="link-preview">
            <span>Razorpay Payment Link</span>
            <strong>{link}</strong>
            <div className="modal-actions">
              <button className="secondary-btn" onClick={() => void navigator.clipboard.writeText(link)}>Copy link</button>
              <button className="secondary-btn" onClick={() => window.open(link, "_blank", "noopener,noreferrer")}>Open link</button>
            </div>
          </div>
        )}
        {error && <p className="form-error">{error}</p>}
        <div className="modal-actions">
          <button className="secondary-btn" onClick={generate}>
            {link ? "Regenerate link" : "Generate payment link"}
          </button>
          <button className="primary-btn" onClick={share} disabled={!link}>
            {shared ? "Shared to WhatsApp" : "Share on WhatsApp"}
          </button>
        </div>
      </div>
    </div>
  );
}
function CustomerDetail({ id }: { id: string }) {
  const customer = useUdhaarStore((s) => s.customers.find((c) => c.id === id));
  const entries = useUdhaarStore((s) => s.ledgerEntries);
  const balance = getBalance(id, entries);
  const [modal, setModal] = useState<"payment" | "reminder" | null>(null);
  if (!customer)
    return (
      <div className="empty">
        <h2>Customer not found</h2>
        <Link href="/customers" className="text-link">
          Back to customers
        </Link>
      </div>
    );
  return (
    <>
      <div className="breadcrumb">
        <Link href="/customers">Customers</Link>
        <ChevronRight size={14} />
        <span>{customer.name}</span>
      </div>
      <section className="detail-hero">
        <div className="detail-person">
          <div className="avatar large">{initials(customer.name)}</div>
          <div>
            <Status value={customer.status} />
            <h2>{customer.name}</h2>
            <p>
              {customer.phone} · Customer since {formatDate(customer.createdAt)}
            </p>
          </div>
        </div>
        <div className="detail-actions">
          <button
            className="secondary-btn"
            onClick={() => setModal("reminder")}
          >
            <Bell size={16} /> Payment reminder
          </button>
          <button className="primary-btn" onClick={() => setModal("payment")}>
            <Plus size={16} /> Record payment
          </button>
        </div>
      </section>
      <section className="detail-balance">
        <div>
          <span className="eyebrow">Outstanding balance</span>
          <strong>{money(balance.outstandingBalance)}</strong>
          <p>
            Derived from {entries.filter((e) => e.customerId === id).length}{" "}
            ledger entries
          </p>
        </div>
        <div className="balance-breakdown">
          <div>
            <span>Total udhaar</span>
            <strong>{money(balance.totalCredit)}</strong>
          </div>
          <div>
            <span>Payments received</span>
            <strong className="amount-positive">
              {money(balance.totalPayment)}
            </strong>
          </div>
          <div>
            <span>Adjustments</span>
            <strong>{money(balance.totalAdjustment)}</strong>
          </div>
        </div>
      </section>
      <section className="detail-grid">
        <div className="panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">Source of truth</span>
              <h3>Transaction ledger</h3>
            </div>
            <button
              className="text-link-btn"
              onClick={() => setModal("payment")}
            >
              Add udhaar <Plus size={14} />
            </button>
          </div>
          <div className="detail-ledger">
            {getEntries(id, entries).map((e) => (
              <div className="ledger-row" key={e.id}>
                <div
                  className={`ledger-sign ${e.type === "payment" ? "payment" : "credit"}`}
                >
                  {e.type === "payment" ? (
                    <ArrowDownLeft size={16} />
                  ) : (
                    <ArrowUpRight size={16} />
                  )}
                </div>
                <div>
                  <strong>{e.description}</strong>
                  <small>
                    {formatDate(e.createdAt)} · <TypeBadge type={e.type} />
                  </small>
                </div>
                <strong
                  className={e.type === "payment" ? "amount-positive" : ""}
                >
                  {e.type === "payment" ? "−" : "+"}
                  {money(e.amount)}
                </strong>
              </div>
            ))}
          </div>
        </div>
        <div className="panel recommendation">
          <div className="panel-head">
            <div>
              <span className="eyebrow">Dummy recommendation</span>
              <h3>Collection queue</h3>
            </div>
            <span className="future-tag">M2</span>
          </div>
          <div className="recommendation-copy">
            <div className="recommendation-icon">
              <Bell size={20} />
            </div>
            <div>
              <strong>Follow up with {customer.name}</strong>
              <p>
                Outstanding for over 30 days. A polite reminder may help close
                this balance.
              </p>
            </div>
          </div>
          <button className="secondary-btn full disabled">
            Generate payment link <ArrowUpRight size={15} />
          </button>
          <small className="muted">
            AI collection engine will be connected in a future release.
          </small>
        </div>
      </section>
      {modal === "payment" && (
        <AddLedger customerId={id} onClose={() => setModal(null)} />
      )}
      {modal === "reminder" && (
        <PaymentReminder customer={customer} onClose={() => setModal(null)} />
      )}
    </>
  );
}
function SettingsPage() {
  return (
    <>
      <section className="page-intro">
        <div>
          <span className="eyebrow">Workspace preferences</span>
          <h2>Settings</h2>
          <p>Manage your merchant profile and future connection points.</p>
        </div>
      </section>
      <div className="settings-grid">
        <div className="panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">Merchant profile</span>
              <h3>Business details</h3>
            </div>
          </div>
          <label>
            Business name
            <input defaultValue="KiranaKart Supplies" />
          </label>
          <label>
            Email address
            <input defaultValue="owner@kir anakart.in" />
          </label>
          <button className="primary-btn">Save changes</button>
        </div>
        <div className="panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">Future integrations</span>
              <h3>Coming in M2 / M5</h3>
            </div>
          </div>
          {[
            "Razorpay Payment Link service",
            "Razorpay webhook handler",
            "FastAPI service",
            "AI collection engine",
          ].map((item) => (
            <div className="integration-row" key={item}>
              <div className="integration-dot" />
              <span>{item}</span>
              <span className="future-tag">Planned</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
export default function UdhaarApp({
  route,
  id,
}: {
  route: "dashboard" | "customers" | "ledger" | "settings" | "detail";
  id?: string;
}) {
  const { hydrate, loading, error } = useUdhaarStore();
  useEffect(() => {
    void hydrate();
  }, [hydrate]);
  if (loading)
    return (
      <Layout>
        <div className="empty">
          <h2>Loading your ledger…</h2>
        </div>
      </Layout>
    );
  if (error)
    return (
      <Layout>
        <div className="empty">
          <h2>Unable to load data</h2>
          <p>{error}</p>
        </div>
      </Layout>
    );
  return (
    <Layout>
      {route === "dashboard" && <Overview />}
      {route === "customers" && <CustomersPage />}
      {route === "ledger" && <LedgerPage />}
      {route === "settings" && <SettingsPage />}
      {route === "detail" && id && <CustomerDetail id={id} />}
    </Layout>
  );
}
