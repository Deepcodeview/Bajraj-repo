import { useState, useEffect } from 'react';
import { Download, RefreshCw, Users, UserCheck, UserX, Clock } from 'lucide-react';
import Sidebar from './Sidebar';
import Header from './Header';
import { getAttendanceReport, getAttendanceSummary, getAttendanceTrend, getLiveLog, exportAttendancePdf } from '../Services/Attendanceservice';
import '../Style/dashboard.css';

const statusColor = { Present: { bg: '#dcfce7', color: '#16a34a' }, Absent: { bg: '#fee2e2', color: '#dc2626' }, 'Checked Out': { bg: '#fef9c3', color: '#ca8a04' } };

const Attendance = () => {
  const [summary, setSummary]   = useState(null);
  const [report, setReport]     = useState(null);
  const [trend, setTrend]       = useState([]);
  const [liveLog, setLiveLog]   = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState('');
  const [date, setDate]         = useState(new Date().toISOString().slice(0, 10));
  const [activeTab, setActiveTab] = useState('report');
  const [exporting, setExporting] = useState(false);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [s, r, t, l] = await Promise.all([
        getAttendanceSummary({ date }),
        getAttendanceReport({ date }),
        getAttendanceTrend({}),
        getLiveLog({ limit: 20 }),
      ]);
      setSummary(s.data);
      setReport(r.data);
      setTrend(t.data?.trend || []);
      setLiveLog(l.data || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [date]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const blob = await exportAttendancePdf({ date });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `attendance-${date}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e.message);
    } finally {
      setExporting(false);
    }
  };

  const summaryCards = summary ? [
    { icon: Users,     label: 'Total Employees', value: summary.totalEmployees, bg: '#eff6ff', color: '#2563eb', iconBg: '#2563eb' },
    { icon: UserCheck, label: 'Present',          value: summary.present,        bg: '#f0fdf4', color: '#16a34a', iconBg: '#16a34a' },
    { icon: UserX,     label: 'Absent',           value: summary.absent,         bg: '#fef2f2', color: '#dc2626', iconBg: '#dc2626' },
    { icon: Clock,     label: 'Attendance Rate',  value: `${summary.attendanceRate}%`, bg: '#fefce8', color: '#ca8a04', iconBg: '#ca8a04' },
  ] : [];

  return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="main-content-wrapper">
        <Header title="Attendance" subtitle="Track employee attendance and shifts" />
        <div className="db-scroll">

          {/* Controls */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <input type="date" value={date} onChange={e => setDate(e.target.value)}
              style={{ padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, color: '#374151' }} />
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={load} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', fontSize: 13, cursor: 'pointer' }}>
                <RefreshCw size={14} /> Refresh
              </button>
              <button onClick={handleExport} disabled={exporting} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', border: 'none', borderRadius: 8, background: '#2563eb', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                <Download size={14} /> {exporting ? 'Exporting...' : 'Export PDF'}
              </button>
            </div>
          </div>

          {error && <div style={{ padding: 16, background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, color: '#dc2626', fontSize: 14 }}>{error}</div>}

          {/* Summary Cards */}
          {summary && (
            <div className="db-stats-row">
              {summaryCards.map(c => (
                <div key={c.label} className="db-stat-card" style={{ background: c.bg, border: `1px solid ${c.color}22` }}>
                  <div className="db-stat-top">
                    <div className="db-stat-icon" style={{ background: c.iconBg }}><c.icon size={20} color="#fff" /></div>
                    <div>
                      <div className="db-stat-label">{c.label}</div>
                      <div className="db-stat-value" style={{ color: c.color }}>{c.value}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Tabs */}
          <div style={{ display: 'flex', gap: 8 }}>
            {['report', 'trend', 'livelog'].map(t => (
              <button key={t} onClick={() => setActiveTab(t)}
                style={{ padding: '8px 18px', borderRadius: 8, border: '1.5px solid', fontSize: 14, fontWeight: 500, cursor: 'pointer', borderColor: activeTab === t ? '#2563eb' : '#d1d5db', background: activeTab === t ? '#2563eb' : '#fff', color: activeTab === t ? '#fff' : '#374151' }}>
                {t === 'report' ? 'Report' : t === 'trend' ? 'Weekly Trend' : 'Live Log'}
              </button>
            ))}
          </div>

          {/* Report Table */}
          {activeTab === 'report' && (
            <div className="db-card" style={{ padding: 0, overflow: 'hidden' }}>
              {loading ? (
                <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                      {['Employee', 'Code', 'Check In', 'Check Out', 'Duration', 'Status'].map(h => (
                        <th key={h} style={{ padding: '12px 20px', textAlign: 'left', fontSize: 13, fontWeight: 600, color: '#6b7280' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(report?.records || []).length === 0 ? (
                      <tr><td colSpan={6} style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No records for this date</td></tr>
                    ) : (report?.records || []).map((r, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                        <td style={{ padding: '13px 20px', fontSize: 14, fontWeight: 500, color: '#111827' }}>{r.name}</td>
                        <td style={{ padding: '13px 20px', fontSize: 14, color: '#374151' }}>{r.employeeCode}</td>
                        <td style={{ padding: '13px 20px', fontSize: 14, color: '#374151' }}>{r.checkIn || '--'}</td>
                        <td style={{ padding: '13px 20px', fontSize: 14, color: '#374151' }}>{r.checkOut || '--'}</td>
                        <td style={{ padding: '13px 20px', fontSize: 14, color: '#374151' }}>{r.duration || '--'}</td>
                        <td style={{ padding: '13px 20px' }}>
                          <span style={{ padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, ...(statusColor[r.status] || { bg: '#f3f4f6', color: '#374151' }), background: (statusColor[r.status] || {}).bg }}>
                            {r.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* Weekly Trend */}
          {activeTab === 'trend' && (
            <div className="db-card">
              <div className="db-card-title" style={{ marginBottom: 16 }}>Weekly Attendance Trend</div>
              {loading ? <div style={{ color: '#6b7280' }}>Loading...</div> : (
                <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', height: 160 }}>
                  {trend.map(d => {
                    const max = Math.max(...trend.map(x => x.present + x.absent), 1);
                    const h = Math.round((d.present / max) * 130);
                    return (
                      <div key={d.day} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontSize: 11, color: '#374151', fontWeight: 600 }}>{d.present}</span>
                        <div style={{ width: '100%', height: h, background: '#6366f1', borderRadius: '4px 4px 0 0', minHeight: 4 }} />
                        <span style={{ fontSize: 12, color: '#6b7280' }}>{d.day}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Live Log */}
          {activeTab === 'livelog' && (
            <div className="db-card" style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{ padding: '14px 20px', borderBottom: '1px solid #e5e7eb', fontWeight: 700, fontSize: 14 }}>Live Face Recognition Log</div>
              {loading ? (
                <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                      {['Employee', 'Code', 'Camera', 'Event', 'Confidence', 'Time'].map(h => (
                        <th key={h} style={{ padding: '11px 20px', textAlign: 'left', fontSize: 13, fontWeight: 600, color: '#6b7280' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {liveLog.length === 0 ? (
                      <tr><td colSpan={6} style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No live events</td></tr>
                    ) : liveLog.map((l, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                        <td style={{ padding: '12px 20px', fontSize: 14, fontWeight: 500 }}>{l.name}</td>
                        <td style={{ padding: '12px 20px', fontSize: 14, color: '#374151' }}>{l.employeeCode || '--'}</td>
                        <td style={{ padding: '12px 20px', fontSize: 14, color: '#374151' }}>{l.camera || '--'}</td>
                        <td style={{ padding: '12px 20px' }}>
                          <span style={{ padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, background: l.event === 'Check-in' ? '#dcfce7' : '#fef9c3', color: l.event === 'Check-in' ? '#16a34a' : '#ca8a04' }}>
                            {l.event}
                          </span>
                        </td>
                        <td style={{ padding: '12px 20px', fontSize: 14, color: '#374151' }}>{l.confidence || '--'}</td>
                        <td style={{ padding: '12px 20px', fontSize: 13, color: '#6b7280' }}>
                          {l.timestamp ? new Date(l.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }) : '--'}
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
    </div>
  );
};

export default Attendance;
