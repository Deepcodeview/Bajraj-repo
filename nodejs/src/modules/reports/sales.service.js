import prisma from "../../config/database.js";

// ─────────────────────────────────────────────────────────────────────────────
// Assumptions (adjust here if your enum values differ):
//   - transactions.status  : voided/cancelled sales use the string "VOID" and
//                             are excluded from all revenue figures.
//   - payments.status      : a payment counts toward "paid" once it is "SUCCESS".
//                             An invoice (transaction) is "Paid" once its
//                             successful payments cover the total_amount.
// ─────────────────────────────────────────────────────────────────────────────

const VOID_STATUS    = "VOID";
const PAID_PAYMENT_STATUS = "SUCCESS";

function getDateRange(startDate, endDate, filter) {
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

  if (filter === "today") {
    return {
      start: new Date(`${today}T00:00:00+05:30`),
      end:   new Date(`${today}T23:59:59+05:30`),
    };
  }

  if (filter === "week") {
    const now = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
    const day = now.getDay(); // 0=Sun, 1=Mon ...
    const diffToMon = (day === 0 ? -6 : 1 - day);
    const monday = new Date(now);
    monday.setDate(now.getDate() + diffToMon);
    const monStr = monday.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
    return {
      start: new Date(`${monStr}T00:00:00+05:30`),
      end:   new Date(`${today}T23:59:59+05:30`),
    };
  }

  if (filter === "month") {
    const first = today.slice(0, 8) + "01";
    return {
      start: new Date(`${first}T00:00:00+05:30`),
      end:   new Date(`${today}T23:59:59+05:30`),
    };
  }

  if (!startDate && !endDate) {
    const first = today.slice(0, 8) + "01";
    return {
      start: new Date(`${first}T00:00:00+05:30`),
      end:   new Date(`${today}T23:59:59+05:30`),
    };
  }

  return {
    start: new Date(`${startDate || today}T00:00:00+05:30`),
    end:   new Date(`${endDate   || today}T23:59:59+05:30`),
  };
}

function previousPeriod(start, end) {
  const spanMs = end.getTime() - start.getTime();
  const prevEnd   = new Date(start.getTime() - 1000);
  const prevStart = new Date(prevEnd.getTime() - spanMs);
  return { start: prevStart, end: prevEnd };
}

function pctChange(current, previous) {
  if (!previous) return current > 0 ? 100 : 0;
  return Math.round(((current - previous) / previous) * 1000) / 10;
}

function monthLabel(d) {
  return d.toLocaleDateString("en-IN", { month: "short", timeZone: "Asia/Kolkata" });
}

function buildHighlights({ totalSales, prevSales, totalCustomers, prevSessionsCount, totalInvoices, prevInvoices, pendingInvoices, topCategory, topProduct }) {
  const lines = [];
  const salesPct = pctChange(totalSales, prevSales);
  lines.push(salesPct >= 0
    ? `Sales increased by ${salesPct}% compared to the previous period.`
    : `Sales declined by ${Math.abs(salesPct)}% compared to the previous period.`);

  if (topCategory) lines.push(`${topCategory.name} is the top-performing category at ${topCategory.pct}% of revenue.`);
  if (topProduct)  lines.push(`${topProduct.name} was the best-selling product by revenue.`);

  const custPct = pctChange(totalCustomers, prevSessionsCount);
  lines.push(custPct >= 0
    ? `Customer footfall grew by ${custPct}% vs. the previous period.`
    : `Customer footfall fell by ${Math.abs(custPct)}% vs. the previous period.`);

  const invPct = pctChange(totalInvoices, prevInvoices);
  lines.push(`Billing count ${invPct >= 0 ? "increased" : "decreased"} by ${Math.abs(invPct)}% vs. the previous period.`);

  if (pendingInvoices > 0) lines.push(`${pendingInvoices} invoice${pendingInvoices === 1 ? "" : "s"} still pending payment.`);

  return lines;
}

export async function getSalesReport(organizationId, { startDate, endDate, storeId, filter }) {
  const { start, end } = getDateRange(startDate, endDate, filter);
  const { start: prevStart, end: prevEnd } = previousPeriod(start, end);

  const org = await prisma.organizations.findFirst({ where: { id: organizationId } });

  const storeWhere = storeId ? { store_id: storeId } : {};

  // ── Current & previous period transactions ─────────────────────────────────
  const [txns, prevTxns] = await Promise.all([
    prisma.transactions.findMany({
      where: {
        organization_id: organizationId,
        transaction_timestamp: { gte: start, lte: end },
        status: { not: VOID_STATUS },
        ...storeWhere,
      },
    }),
    prisma.transactions.findMany({
      where: {
        organization_id: organizationId,
        transaction_timestamp: { gte: prevStart, lte: prevEnd },
        status: { not: VOID_STATUS },
        ...storeWhere,
      },
      select: { id: true, total_amount: true },
    }),
  ]);

  const txnIds = txns.map(t => t.id);

  const totalSales   = txns.reduce((s, t) => s + Number(t.total_amount || 0), 0);
  const prevSales     = prevTxns.reduce((s, t) => s + Number(t.total_amount || 0), 0);
  const totalInvoices = txns.length;
  const prevInvoices  = prevTxns.length;
  const avgOrderValue = totalInvoices ? totalSales / totalInvoices : 0;
  const prevAOV        = prevInvoices ? prevSales / prevInvoices : 0;

  // ── Line items (items sold, top products, category split) ──────────────────
  const items = txnIds.length
    ? await prisma.transaction_items.findMany({
        where: { organization_id: organizationId, transaction_id: { in: txnIds } },
      })
    : [];

  const itemsSold = items.reduce((s, it) => s + Number(it.quantity || 0), 0);

  const productIds = [...new Set(items.map(it => it.product_id).filter(Boolean))];
  const products = productIds.length
    ? await prisma.products.findMany({ where: { id: { in: productIds } } })
    : [];
  const productCategory = new Map(products.map(p => [p.id, p.category || "Uncategorized"]));

  const productAgg = new Map(); // key: product_id||name -> { name, category, units, revenue }
  const categoryAgg = new Map(); // category -> revenue

  for (const it of items) {
    const key      = it.product_id || it.product_name;
    const category = it.product_id ? (productCategory.get(it.product_id) || "Uncategorized") : "Uncategorized";
    const revenue  = Number(it.total_price || 0);
    const qty      = Number(it.quantity || 0);

    if (!productAgg.has(key)) {
      productAgg.set(key, { name: it.product_name, category, units: 0, revenue: 0 });
    }
    const p = productAgg.get(key);
    p.units   += qty;
    p.revenue += revenue;

    categoryAgg.set(category, (categoryAgg.get(category) || 0) + revenue);
  }

  const topProducts = [...productAgg.values()]
    .sort((a, b) => b.revenue - a.revenue)
    .slice(0, 5);

  const categoryTotal = [...categoryAgg.values()].reduce((s, v) => s + v, 0) || 1;
  const salesByCategory = [...categoryAgg.entries()]
    .map(([name, revenue]) => ({ name, revenue, pct: Math.round((revenue / categoryTotal) * 1000) / 10 }))
    .sort((a, b) => b.revenue - a.revenue);

  // ── Payments (billing status + payment method split) ────────────────────────
  const payments = txnIds.length
    ? await prisma.payments.findMany({
        where: { organization_id: organizationId, transaction_id: { in: txnIds } },
      })
    : [];

  const paidByTxn = new Map();
  for (const p of payments) {
    if (p.status !== PAID_PAYMENT_STATUS) continue;
    paidByTxn.set(p.transaction_id, (paidByTxn.get(p.transaction_id) || 0) + Number(p.amount || 0));
  }
  const paidInvoices = txns.filter(t => (paidByTxn.get(t.id) || 0) >= Number(t.total_amount || 0)).length;
  const pendingInvoices = totalInvoices - paidInvoices;

  const methodAgg = new Map();
  let paidTotal = 0;
  for (const p of payments) {
    if (p.status !== PAID_PAYMENT_STATUS) continue;
    const amt = Number(p.amount || 0);
    methodAgg.set(p.payment_mode, (methodAgg.get(p.payment_mode) || 0) + amt);
    paidTotal += amt;
  }
  const paymentSplit = [...methodAgg.entries()]
    .map(([mode, amount]) => ({ mode, amount, pct: paidTotal ? Math.round((amount / paidTotal) * 1000) / 10 : 0 }))
    .sort((a, b) => b.amount - a.amount);

  const invoiceAmounts = txns.map(t => Number(t.total_amount || 0)).filter(a => a > 0);
  const highestInvoice = invoiceAmounts.length ? Math.max(...invoiceAmounts) : 0;
  const lowestInvoice  = invoiceAmounts.length ? Math.min(...invoiceAmounts) : 0;

  // ── Customers (footfall via customer_sessions) ──────────────────────────────
  const sessions = await prisma.customer_sessions.findMany({
    where: {
      organization_id: organizationId,
      start_time: { gte: start, lte: end },
      ...storeWhere,
    },
  });

  const trackingIds = [...new Set(sessions.map(s => s.customer_tracking_id).filter(Boolean))];
  const priorSessions = trackingIds.length
    ? await prisma.customer_sessions.findMany({
        where: {
          organization_id: organizationId,
          customer_tracking_id: { in: trackingIds },
          start_time: { lt: start },
        },
        select: { customer_tracking_id: true },
      })
    : [];
  const priorSet = new Set(priorSessions.map(s => s.customer_tracking_id));
  const repeatCustomers = trackingIds.filter(id => priorSet.has(id)).length;
  const totalCustomers  = trackingIds.length || sessions.length;
  const newCustomers    = Math.max(totalCustomers - repeatCustomers, 0);
  const repeatPct = totalCustomers ? Math.round((repeatCustomers / totalCustomers) * 1000) / 10 : 0;
  const newPct    = totalCustomers ? Math.round((newCustomers   / totalCustomers) * 1000) / 10 : 0;

  const durations = sessions
    .filter(s => s.end_time)
    .map(s => (new Date(s.end_time) - new Date(s.start_time)) / 60000);
  const avgVisitMinutes = durations.length ? durations.reduce((a, b) => a + b, 0) / durations.length : 0;

  // ── Prior-period customer count (for % change) ──────────────────────────────
  const prevSessionsCount = await prisma.customer_sessions.count({
    where: { organization_id: organizationId, start_time: { gte: prevStart, lte: prevEnd }, ...storeWhere },
  });

  // ── Sales trend: last 6 calendar months (ending with the report month) ──────
  const trend = [];
  const anchor = new Date(end);
  for (let i = 5; i >= 0; i--) {
    const mStart = new Date(anchor.getFullYear(), anchor.getMonth() - i, 1);
    const mEnd   = new Date(anchor.getFullYear(), anchor.getMonth() - i + 1, 0, 23, 59, 59);
    const mTxns  = await prisma.transactions.findMany({
      where: {
        organization_id: organizationId,
        transaction_timestamp: { gte: mStart, lte: mEnd },
        status: { not: VOID_STATUS },
        ...storeWhere,
      },
      select: { total_amount: true },
    });
    trend.push({
      label: monthLabel(mStart),
      value: mTxns.reduce((s, t) => s + Number(t.total_amount || 0), 0),
    });
  }

  // ── Stores covered ───────────────────────────────────────────────────────────
  const stores = await prisma.stores.findMany({
    where: { organization_id: organizationId, ...(storeId && { id: storeId }) },
    select: { name: true },
  });

  const highlights = buildHighlights({
    totalSales, prevSales,
    totalCustomers, prevSessionsCount,
    totalInvoices, prevInvoices,
    pendingInvoices,
    topCategory: salesByCategory[0],
    topProduct: topProducts[0],
  });

  return {
    organization: { id: org.id, name: org.name },
    dateRange:    { start: start.toISOString(), end: end.toISOString() },
    stores:       stores.map(s => s.name),
    highlights,

    kpis: {
      totalSales,       totalSalesChangePct:  pctChange(totalSales, prevSales),
      totalCustomers,   totalCustomersChangePct: pctChange(totalCustomers, prevSessionsCount),
      itemsSold,
      totalInvoices,    totalInvoicesChangePct: pctChange(totalInvoices, prevInvoices),
      avgOrderValue,    avgOrderValueChangePct: pctChange(avgOrderValue, prevAOV),
    },

    trend,
    salesByCategory,
    topProducts,

    customerInsights: {
      totalCustomers,
      repeatCustomers, repeatPct,
      newCustomers,    newPct,
      avgVisitMinutes,
    },

    billing: {
      totalInvoices,
      paidInvoices,    paidPct: totalInvoices ? Math.round((paidInvoices / totalInvoices) * 1000) / 10 : 0,
      pendingInvoices, pendingPct: totalInvoices ? Math.round((pendingInvoices / totalInvoices) * 1000) / 10 : 0,
      totalBilling: totalSales,
      avgInvoice:   avgOrderValue,
      highestInvoice,
      lowestInvoice,
    },

    paymentSplit,
  };
}
