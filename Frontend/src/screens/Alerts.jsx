import { useState, useEffect } from 'react';
import { AlertTriangle, Info, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import Sidebar from './Sidebar';
import Header from './Header';
import { getAlerts, acknowledgeAlert, resolveAlert } from '../Services/Alertsservice';
import '../Style/Alerts.css';

const severityDot    = { HIGH: 'dot-red', MEDIUM: 'dot-orange', LOW: 'dot-yellow', CRITICAL: 'dot-red' };
const severityBadge  = { HIGH: 'badge-high', MEDIUM: 'badge-medium', LOW: 'badge-low', CRITICAL: 'badge-critical' };
const statusBadge    = { OPEN: 'status-new', ACKNOWLEDGED: 'status-acknowledged', RESOLVED: 'status-resolved' };
const statusLabel    = { OPEN: 'Open', ACKNOWLEDGED: 'Acknowledged', RESOLVED: 'Resolved' };

const AlertIcon = ({ severity }) => {
  if (severity === 'LOW') return <Info size={20} className="icon-info" />;
  if (severity === 'HIGH' || severity === 'CRITICAL') return <AlertTriangle size={20} className="icon-warning-red" />;
  return <AlertTriangle size={20} className="icon-warning-orange" />;
};

const TABS = ['All', 'OPEN', 'ACKNOWLEDGED', 'RESOLVED'];

const Alerts = () => {
  const [alerts, setAlerts]     = useState([]);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState('');
  const [activeTab, setActiveTab] = useState(0);
  const [page, setPage]         = useState(1);
  const LIMIT = 10;

  const load = async (tab = activeTab, pg = page) => {
    setLoading(true);
    setError('');
    try {
      const params = { page: pg, limit: LIMIT };
      if (TABS[tab] !== 'All') params.status = TABS[tab];
      const res = await getAlerts(params);
      setAlerts(res.data || []);
      setTotal(res.pagination?.total || 0);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(activeTab, page); }, [activeTab, page]);

  const handleTab = (i) => { setActiveTab(i); setPage(1); };

  const handleAcknowledge = async (id) => {
    try { await acknowledgeAlert(id); load(); } catch (e) { alert(e.message); }
  };

  const handleResolve = async (id) => {
    try { await resolveAlert(id); load(); } catch (e) { alert(e.message); }
  };

  const totalPages = Math.ceil(total / LIMIT);

  const formatTime = (ts) => ts ? new Date(ts).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }) : '--';

  return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="main-content-wrapper">
        <Header title="Alerts" subtitle="Monitor and manage all store alerts" />
        <main className="main-content" style={{ padding: '20px 24px', overflowY: 'auto', flex: 1 }}>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div className="alerts-tabs" style={{ marginBottom: 0 }}>
              {TABS.map((tab, i) => (
                <button key={i} className={`tab-btn ${activeTab === i ? 'tab-active' : ''}`} onClick={() => handleTab(i)}>
                  {tab}
                </button>
              ))}
            </div>
            <button onClick={() => load()} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', fontSize: 13, cursor: 'pointer', color: '#374151' }}>
              <RefreshCw size={14} /> Refresh
            </button>
          </div>

          <div className="alerts-table-wrapper">
            {loading ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
            ) : error ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#ef4444' }}>{error}</div>
            ) : (
              <table className="alerts-table">
                <thead>
                  <tr>
                    <th>Alert</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Time</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.length === 0 ? (
                    <tr><td colSpan={5} style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No alerts found</td></tr>
                  ) : alerts.map(a => (
                    <tr key={a.id}>
                      <td className="alert-name-cell">
                        <AlertIcon severity={a.severity} />
                        <div>
                          <div style={{ fontWeight: 600, fontSize: 14 }}>{a.title}</div>
                          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{a.alert_code}</div>
                        </div>
                      </td>
                      <td>
                        <div className="severity-cell">
                          <span className={`severity-dot ${severityDot[a.severity] || 'dot-yellow'}`} />
                          <span className={`severity-badge ${severityBadge[a.severity] || 'badge-medium'}`}>{a.severity}</span>
                        </div>
                      </td>
                      <td>
                        <span className={`status-badge ${statusBadge[a.status] || 'status-new'}`}>{statusLabel[a.status] || a.status}</span>
                      </td>
                      <td style={{ fontSize: 13, color: '#6b7280' }}>{formatTime(a.created_at)}</td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          {a.status === 'OPEN' && (
                            <button onClick={() => handleAcknowledge(a.id)} style={{ padding: '4px 10px', border: '1px solid #93c5fd', borderRadius: 6, background: '#eff6ff', color: '#2563eb', fontSize: 12, cursor: 'pointer', fontWeight: 500 }}>
                              Acknowledge
                            </button>
                          )}
                          {a.status !== 'RESOLVED' && (
                            <button onClick={() => handleResolve(a.id)} style={{ padding: '4px 10px', border: '1px solid #86efac', borderRadius: 6, background: '#f0fdf4', color: '#16a34a', fontSize: 12, cursor: 'pointer', fontWeight: 500 }}>
                              Resolve
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div className="alerts-pagination">
              <span className="pagination-info">Showing {alerts.length} of {total} alerts</span>
              <div className="pagination-controls">
                <button className="page-btn" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}><ChevronLeft size={15} /></button>
                {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => i + 1).map(n => (
                  <button key={n} className={`page-btn ${page === n ? 'page-active' : ''}`} onClick={() => setPage(n)}>{n}</button>
                ))}
                <button className="page-btn" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}><ChevronRight size={15} /></button>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};

export default Alerts;
