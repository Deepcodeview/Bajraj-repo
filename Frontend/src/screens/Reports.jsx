import { useState, useEffect } from 'react';
import { FileText, Download, Plus, RefreshCw, Calendar } from 'lucide-react';
import Sidebar from './Sidebar';
import Header from './Header';
import { getReportsSummary, getReportsHistory, generateReport, downloadReport, getScheduledReports, createScheduledReport } from '../Services/Reportservice';
import '../Style/dashboard.css';

const REPORT_TYPES = ['attendance', 'employee', 'alert', 'footfall'];

const Reports = () => {
  const [summary, setSummary]     = useState(null);
  const [history, setHistory]     = useState([]);
  const [scheduled, setScheduled] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [activeTab, setActiveTab] = useState('history');
  const [generating, setGenerating] = useState(false);
  const [genForm, setGenForm]     = useState({ type: 'attendance', date: new Date().toISOString().slice(0, 10) });
  const [showGenModal, setShowGenModal] = useState(false);
  const [showSchedModal, setShowSchedModal] = useState(false);
  const [schedForm, setSchedForm] = useState({ name: '', type: 'attendance', frequency: 'daily' });
  const [scheduling, setScheduling] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [s, h, sc] = await Promise.all([
        getReportsSummary(),
        getReportsHistory({}),
        getScheduledReports(),
      ]);
      setSummary(s.data);
      setHistory(h.data?.reports || []);
      setScheduled(sc.data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleGenerate = async (e) => {
    e.preventDefault();
    setGenerating(true);
    try {
      await generateReport(genForm);
      setShowGenModal(false);
      load();
    } catch (e) {
      alert(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleSchedule = async (e) => {
    e.preventDefault();
    setScheduling(true);
    try {
      await createScheduledReport(schedForm);
      setShowSchedModal(false);
      setSchedForm({ name: '', type: 'attendance', frequency: 'daily' });
      load();
    } catch (e) {
      alert(e.message);
    } finally {
      setScheduling(false);
    }
  };

  const handleDownload = async (id, name) => {
    try {
      const blob = await downloadReport(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `${name}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e.message);
    }
  };

  const summaryCards = summary ? [
    { label: 'Total Generated', value: summary.totalGenerated,   color: '#2563eb', bg: '#eff6ff' },
    { label: 'Scheduled',       value: summary.scheduledReports, color: '#7c3aed', bg: '#f5f3ff' },
    { label: 'Most Requested',  value: summary.mostRequested,    color: '#16a34a', bg: '#f0fdf4' },
    { label: 'Last Report',     value: summary.lastReport?.name || 'None', color: '#ca8a04', bg: '#fefce8' },
  ] : [];

  return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="main-content-wrapper">
        <Header title="Reports" subtitle="Generate and manage store reports" />
        <div className="db-scroll">

          {/* Summary Cards */}
          {summary && (
            <div className="db-stats-row">
              {summaryCards.map(c => (
                <div key={c.label} className="db-stat-card" style={{ background: c.bg }}>
                  <div className="db-stat-label">{c.label}</div>
                  <div className="db-stat-value" style={{ color: c.color, fontSize: 20, marginTop: 6 }}>{c.value}</div>
                </div>
              ))}
            </div>
          )}

          {/* Tabs + Generate Button */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 8 }}>
              {['history', 'scheduled'].map(t => (
                <button key={t} onClick={() => setActiveTab(t)}
                  style={{ padding: '8px 18px', borderRadius: 8, border: '1.5px solid', fontSize: 14, fontWeight: 500, cursor: 'pointer', borderColor: activeTab === t ? '#2563eb' : '#d1d5db', background: activeTab === t ? '#2563eb' : '#fff', color: activeTab === t ? '#fff' : '#374151' }}>
                  {t === 'history' ? 'Report History' : 'Scheduled Reports'}
                </button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={load} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', fontSize: 13, cursor: 'pointer' }}>
                <RefreshCw size={14} /> Refresh
              </button>
              <button onClick={() => setShowGenModal(true)} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', border: 'none', borderRadius: 8, background: '#2563eb', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                <Plus size={15} /> Generate Report
              </button>
              <button onClick={() => setShowSchedModal(true)} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', border: '1px solid #7c3aed', borderRadius: 8, background: '#f5f3ff', color: '#7c3aed', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                <Calendar size={15} /> Schedule
              </button>
            </div>
          </div>

          {/* Report History */}
          {activeTab === 'history' && (
            <div className="db-card" style={{ padding: 0, overflow: 'hidden' }}>
              {loading ? (
                <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                      {['Report Name', 'Type', 'Date Range', 'Generated At', 'Size', 'Status', ''].map(h => (
                        <th key={h} style={{ padding: '12px 20px', textAlign: 'left', fontSize: 13, fontWeight: 600, color: '#6b7280' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {history.length === 0 ? (
                      <tr><td colSpan={7} style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No reports generated yet</td></tr>
                    ) : history.map(r => (
                      <tr key={r.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                        <td style={{ padding: '13px 20px', fontSize: 14, fontWeight: 500, color: '#111827', display: 'flex', alignItems: 'center', gap: 8 }}>
                          <FileText size={16} color="#6366f1" /> {r.name}
                        </td>
                        <td style={{ padding: '13px 20px', fontSize: 13, color: '#374151', textTransform: 'capitalize' }}>{r.type}</td>
                        <td style={{ padding: '13px 20px', fontSize: 13, color: '#374151' }}>{r.dateRange}</td>
                        <td style={{ padding: '13px 20px', fontSize: 13, color: '#6b7280' }}>{new Date(r.generatedAt).toLocaleString('en-IN')}</td>
                        <td style={{ padding: '13px 20px', fontSize: 13, color: '#374151' }}>{r.fileSize}</td>
                        <td style={{ padding: '13px 20px' }}>
                          <span style={{ padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, background: '#dcfce7', color: '#16a34a' }}>{r.status}</span>
                        </td>
                        <td style={{ padding: '13px 20px' }}>
                          <button onClick={() => handleDownload(r.id, r.name)} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 12px', border: '1px solid #d1d5db', borderRadius: 6, background: '#fff', fontSize: 13, cursor: 'pointer', color: '#374151' }}>
                            <Download size={13} /> Download
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* Scheduled Reports */}
          {activeTab === 'scheduled' && (
            <div className="db-card" style={{ padding: 0, overflow: 'hidden' }}>
              {loading ? (
                <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                      {['Name', 'Type', 'Frequency', 'Next Run', 'Status'].map(h => (
                        <th key={h} style={{ padding: '12px 20px', textAlign: 'left', fontSize: 13, fontWeight: 600, color: '#6b7280' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {scheduled.length === 0 ? (
                      <tr><td colSpan={5} style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No scheduled reports</td></tr>
                    ) : scheduled.map(r => (
                      <tr key={r.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                        <td style={{ padding: '13px 20px', fontSize: 14, fontWeight: 500, color: '#111827', display: 'flex', alignItems: 'center', gap: 8 }}>
                          <Calendar size={15} color="#6366f1" /> {r.name}
                        </td>
                        <td style={{ padding: '13px 20px', fontSize: 13, color: '#374151', textTransform: 'capitalize' }}>{r.type}</td>
                        <td style={{ padding: '13px 20px', fontSize: 13, color: '#374151', textTransform: 'capitalize' }}>{r.frequency}</td>
                        <td style={{ padding: '13px 20px', fontSize: 13, color: '#6b7280' }}>{new Date(r.nextRun).toLocaleString('en-IN')}</td>
                        <td style={{ padding: '13px 20px' }}>
                          <span style={{ padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, background: '#dcfce7', color: '#16a34a' }}>{r.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

        </div>
      </div>

      {/* Generate Modal */}
      {showGenModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: '#fff', borderRadius: 12, padding: 28, width: 400 }}>
            <h3 style={{ margin: '0 0 20px', fontSize: 17, fontWeight: 700 }}>Generate Report</h3>
            <form onSubmit={handleGenerate}>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 5 }}>Report Type</label>
                <select value={genForm.type} onChange={e => setGenForm(p => ({ ...p, type: e.target.value }))}
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 7, fontSize: 14 }}>
                  {REPORT_TYPES.map(t => <option key={t} value={t} style={{ textTransform: 'capitalize' }}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
                </select>
              </div>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 5 }}>Date</label>
                <input type="date" value={genForm.date} onChange={e => setGenForm(p => ({ ...p, date: e.target.value }))}
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 7, fontSize: 14, boxSizing: 'border-box' }} />
              </div>
              <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
                <button type="button" onClick={() => setShowGenModal(false)} style={{ flex: 1, padding: 9, border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', fontSize: 14, cursor: 'pointer' }}>Cancel</button>
                <button type="submit" disabled={generating} style={{ flex: 1, padding: 9, border: 'none', borderRadius: 8, background: '#2563eb', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
                  {generating ? 'Generating...' : 'Generate'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* Schedule Modal */}
      {showSchedModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: '#fff', borderRadius: 12, padding: 28, width: 400 }}>
            <h3 style={{ margin: '0 0 20px', fontSize: 17, fontWeight: 700 }}>Schedule Report</h3>
            <form onSubmit={handleSchedule}>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 5 }}>Report Name</label>
                <input required value={schedForm.name} onChange={e => setSchedForm(p => ({ ...p, name: e.target.value }))}
                  placeholder="e.g. Daily Attendance"
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 7, fontSize: 14, boxSizing: 'border-box' }} />
              </div>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 5 }}>Report Type</label>
                <select value={schedForm.type} onChange={e => setSchedForm(p => ({ ...p, type: e.target.value }))}
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 7, fontSize: 14 }}>
                  {REPORT_TYPES.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
                </select>
              </div>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 5 }}>Frequency</label>
                <select value={schedForm.frequency} onChange={e => setSchedForm(p => ({ ...p, frequency: e.target.value }))}
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 7, fontSize: 14 }}>
                  {['daily','weekly','monthly'].map(f => <option key={f} value={f}>{f.charAt(0).toUpperCase() + f.slice(1)}</option>)}
                </select>
              </div>
              <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
                <button type="button" onClick={() => setShowSchedModal(false)} style={{ flex: 1, padding: 9, border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', fontSize: 14, cursor: 'pointer' }}>Cancel</button>
                <button type="submit" disabled={scheduling} style={{ flex: 1, padding: 9, border: 'none', borderRadius: 8, background: '#7c3aed', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
                  {scheduling ? 'Scheduling...' : 'Schedule'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Reports;
