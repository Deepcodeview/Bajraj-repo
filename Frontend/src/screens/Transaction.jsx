import { useState, useEffect } from 'react';
import { ArrowDown, ArrowUp, CreditCard, Download, ReceiptText, RotateCcw, ShoppingCart, TrendingUp } from 'lucide-react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import Sidebar from './Sidebar';
import Header from './Header';
import { getTransactions, getTransactionSummary, getTransactionTrend, getPaymentMethodSplit } from '../Services/Transactionservice';
import '../Style/Transaction.css';

const TxCard = ({ children, className = '' }) => <section className={`tx-card ${className}`}>{children}</section>;

function TxStat({ icon: Icon, label, value, note, down = false }) {
  return (
    <TxCard className="tx-stat">
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        <small className={down ? 'down' : ''}>{down ? '↓' : '↑'} {note} vs yesterday</small>
      </div>
      <span className={down ? 'tx-stat-icon red' : 'tx-stat-icon'}><Icon size={18} /></span>
      <div className="tx-spark">{[8, 14, 11, 22, 16, 25, 20, 32].map((n, i) => <i key={i} style={{ height: n }} />)}</div>
    </TxCard>
  );
}

function Title({ children, action }) {
  return <div className="tx-title"><h2>{children}</h2>{action}</div>;
}

const fmt = (n) => Number(n || 0).toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });
const fmtTime = (ts) => ts ? new Date(ts).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }) : '--';

export default function Transaction() {
  const [period, setPeriod] = useState('Today');
  const [transactions, setTransactions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [trend, setTrend] = useState([]);
  const [paymentSplit, setPaymentSplit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const [txRes, summaryRes, trendRes, splitRes] = await Promise.allSettled([
          getTransactions({ limit: 20, page: 1 }),
          getTransactionSummary({}),
          getTransactionTrend({}),
          getPaymentMethodSplit({}),
        ]);

        if (txRes.status === 'fulfilled') setTransactions(txRes.value?.data || txRes.value || []);
        if (summaryRes.status === 'fulfilled') setSummary(summaryRes.value?.data || summaryRes.value);
        if (trendRes.status === 'fulfilled') setTrend(trendRes.value?.data?.trend || trendRes.value?.trend || []);
        if (splitRes.status === 'fulfilled') setPaymentSplit(splitRes.value?.data || splitRes.value || []);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  // Derive summary values
  const totalSales       = summary?.totalSales       ?? summary?.total_amount       ?? 0;
  const totalTxns        = summary?.totalTransactions ?? summary?.total_transactions ?? transactions.length;
  const avgTxnValue      = summary?.avgTransactionValue ?? (totalTxns > 0 ? totalSales / totalTxns : 0);
  const refunds          = summary?.refunds           ?? summary?.refund_count       ?? 0;

  // Payment split for pie chart
  const pieColors = ['#4f46e5', '#3b82f6', '#43bfa5'];
  const pieData = paymentSplit.length > 0
    ? paymentSplit.map(p => ({ name: p.payment_mode || p.name, value: Number(p.count || p.value || 0) }))
    : [{ name: 'Card', value: 1 }];

  // Trend data for chart
  const chartData = trend.length > 0
    ? trend.map(t => ({ time: t.label || t.hour || t.time, value: Number(t.total || t.value || 0) }))
    : [];

  const statusClass = (s) => {
    const v = (s || '').toLowerCase();
    if (v === 'completed' || v === 'success') return 'completed';
    if (v === 'pending') return 'pending';
    if (v === 'refunded' || v === 'cancelled') return 'refunded';
    return 'pending';
  };

  return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="main-content-wrapper">
        <Header title="Transactions" subtitle="Monitor sales, billing and payment activity" />
        <main className="tx-scroll">

          <div className="tx-actions">
            <div className="tx-search">Search transaction ID, customer...</div>
            <button className="tx-button"><Download size={14} /> Export Report</button>
          </div>

          {error && <div style={{ padding: '10px 14px', background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 7, color: '#dc2626', fontSize: 13 }}>{error}</div>}

          <div className="tx-stats">
            <TxStat icon={ShoppingCart}  label="Total Sales Today"         value={loading ? '...' : fmt(totalSales)}   note="--" />
            <TxStat icon={ReceiptText}   label="Total Transactions"         value={loading ? '...' : totalTxns}         note="--" />
            <TxStat icon={CreditCard}    label="Avg. Transaction Value"     value={loading ? '...' : fmt(avgTxnValue)}  note="--" />
            <TxStat icon={RotateCcw}     label="Refunds/Cancellations"      value={loading ? '...' : refunds}           note="--" down />
          </div>

          <div className="tx-grid main">
            <TxCard>
              <Title action={
                <div className="tx-tabs">
                  {['Today', '7D', '30D'].map(x => (
                    <button onClick={() => setPeriod(x)} className={period === x ? 'active' : ''} key={x}>{x}</button>
                  ))}
                </div>
              }>Sales Trend</Title>
              <div className="tx-chart">
                {chartData.length > 0 ? (
                  <ResponsiveContainer>
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id="txfill" x1="0" y1="0" x2="0" y2="1">
                          <stop stopColor="#4f46e5" stopOpacity=".32" />
                          <stop offset="1" stopColor="#4f46e5" stopOpacity="0" />
                        </linearGradient>
                      </defs>
                      <CartesianGrid vertical={false} stroke="#edf0f5" />
                      <XAxis dataKey="time" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
                      <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
                      <Tooltip />
                      <Area dataKey="value" stroke="#4f46e5" fill="url(#txfill)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#9ca3af', fontSize: 12 }}>
                    {loading ? 'Loading...' : 'No trend data available'}
                  </div>
                )}
              </div>
            </TxCard>

            <TxCard>
              <Title>Payment Method Split</Title>
              <div className="tx-payment">
                <div className="tx-donut">
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie data={pieData} dataKey="value" innerRadius={48} outerRadius={72} stroke="#fff" strokeWidth={2}>
                        {pieData.map((_, i) => <Cell fill={pieColors[i % pieColors.length]} key={i} />)}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <span><b>{totalTxns}</b>Transactions</span>
                </div>
                <div className="tx-legend">
                  {pieData.map((p, i) => (
                    <p key={p.name}>
                      <i style={{ background: pieColors[i % pieColors.length], height: 9, width: 9, borderRadius: '50%', display: 'inline-block' }} />
                      {p.name} <b style={{ marginLeft: 'auto' }}>{p.value}</b>
                    </p>
                  ))}
                </div>
              </div>
            </TxCard>
          </div>

          <TxCard>
            <Title>Recent Transactions</Title>
            <div className="tx-table-wrap">
              {loading ? (
                <div style={{ padding: 30, textAlign: 'center', color: '#9ca3af', fontSize: 12 }}>Loading...</div>
              ) : transactions.length === 0 ? (
                <div style={{ padding: 30, textAlign: 'center', color: '#9ca3af', fontSize: 12 }}>No transactions found</div>
              ) : (
                <table className="tx-table">
                  <thead>
                    <tr>
                      {['Transaction ID', 'Invoice', 'Amount', 'Status', 'Currency', 'Source', 'Time'].map(x => <th key={x}>{x}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map(tx => (
                      <tr key={tx.id}>
                        <td>{tx.transaction_code || tx.id?.slice(0, 8)}</td>
                        <td>{tx.invoice_number || tx.pos_reference || '--'}</td>
                        <td className="amount">{fmt(tx.total_amount)}</td>
                        <td><span className={`tx-status ${statusClass(tx.status)}`}>{tx.status}</span></td>
                        <td>{tx.currency || 'INR'}</td>
                        <td>{tx.source_system || '--'}</td>
                        <td>{fmtTime(tx.transaction_timestamp || tx.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </TxCard>

        </main>
      </div>
    </div>
  );
}
