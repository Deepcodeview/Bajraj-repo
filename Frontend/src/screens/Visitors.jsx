import { useState, useEffect } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import { ChevronRight } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, PieChart, Pie, Cell } from 'recharts';
import { fetchCustomerSessions, fetchCustomerSummary, fetchCustomerReport } from '../Services/Visitorsservice';
import '../Style/Visitors.css';

const pieData = [
  { name: 'Morning 30% (38)',   value: 30, color: '#6366f1' },
  { name: 'Afternoon 45% (58)', value: 45, color: '#22c55e' },
  { name: 'Evening 25% (32)',   value: 25, color: '#a855f7' },
];
const overviewBars = [40, 60, 80, 100, 120, 90, 70, 110, 130, 85, 60, 40, 30];
const funnelSteps = [
  { label: 'Store Entries',      count: 128, pct: 100 },
  { label: 'Browsed Products',   count: 88,  pct: 69 },
  { label: 'Tried / Interested', count: 64,  pct: 50 },
  { label: 'Billing Counter',    count: 43,  pct: 34 },
  { label: 'Purchase Completed', count: 31,  pct: 24 },
];
const segments = [
  { name: 'Browsers',        pct: 45, color: '#6366f1' },
  { name: 'Quick Shoppers',  pct: 30, color: '#22c55e' },
  { name: 'Window Shoppers', pct: 15, color: '#f59e0b' },
  { name: 'High-Intent',     pct: 10, color: '#10b981' },
];
const heatZones = [
  { label: 'Entrance',     count: 48, color: '#6366f1' },
  { label: 'Main Floor',   count: 76, color: '#8b5cf6' },
  { label: 'Fitting Room', count: 55, color: '#a855f7' },
  { label: 'Billing',      count: 62, color: '#7c3aed' },
  { label: 'Checkout',     count: 65, color: '#c026d3' },
];
const journeySteps = ['Entrance', 'Main Floor', 'Fitting Room', 'Billing'];

const Visitors = () => {
  const [summary,  setSummary]  = useState(null);
  const [report,   setReport]   = useState(null);
  const [sessions, setSessions] = useState([]);

  useEffect(() => {
    const load = async () => {
      try {
        const [sessRes, summ, rep] = await Promise.all([
          fetchCustomerSessions({ limit: 20 }),
          fetchCustomerSummary(),
          fetchCustomerReport(),
        ]);
        setSessions(sessRes?.data || []);
        setSummary(summ || null);
        setReport(rep || null);
      } catch {}
    };
    load();
  }, []);

  const totalToday   = summary?.totalVisitors  ?? report?.totalVisitors ?? 128;
  const insideNow    = summary?.active          ?? 12;
  const totalEntries = summary?.totalVisitors   ?? 128;
  const totalExits   = summary?.completed       ?? 116;
  const avgDwell     = summary?.avgDurationMin  ? `${summary.avgDurationMin}m` : '18m 24s';
  const peakTime     = '3:00 PM';

  const barData = report?.records?.length > 0
    ? (() => {
        const map = {};
        report.records.forEach(r => {
          if (r.entryTime) { const h = r.entryTime.split(':')[0]; map[h] = (map[h]||0)+1; }
        });
        return Object.entries(map).map(([h,v]) => ({ day: `${h}:00`, v }));
      })()
    : [
        { day: 'Mon', v: 80 }, { day: 'Tue', v: 95 }, { day: 'Wed', v: 110 },
        { day: 'Thu', v: 130 }, { day: 'Fri', v: 150 }, { day: 'Sat', v: 170 }, { day: 'Sun', v: 120 },
      ];

  return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="main-content-wrapper">
        <Header title="Visitors" subtitle="Track and analyze visitor footfall and behavior" />
        <div className="vp-scroll">

          {/* Stat Cards */}
          <div className="vp-stats-row">
            {[
              { label: 'Total Visitors Today', value: totalToday,   trend: '↑18.7%',     trendColor: 'green' },
              { label: 'Currently Inside',     value: insideNow,    trend: '+Live',       trendColor: 'green' },
              { label: 'Total Entries',        value: totalEntries, trend: '↑18.7%',     trendColor: 'green' },
              { label: 'Total Exits',          value: totalExits,   trend: '↓12.4%',     trendColor: 'red' },
              { label: 'Avg. Dwell Time',      value: avgDwell,     trend: '↑6.3%',      trendColor: 'green' },
              { label: 'Peak Time',            value: peakTime,     trend: '65 Visitors', trendColor: 'blue' },
            ].map(s => (
              <div className="vp-stat-card" key={s.label}>
                <div className="vp-stat-label">{s.label}</div>
                <div className="vp-stat-value">{s.value}</div>
                <span className={`vp-stat-trend ${s.trendColor}`}>{s.trend}</span>
              </div>
            ))}
          </div>

          {/* Charts Row */}
          <div className="vp-charts-row">
            <div className="vp-card">
              <div className="vp-card-header">
                <span className="vp-card-title">Visitors Overview</span>
                <div className="vp-tabs"><span className="vp-tab active">Today</span><span className="vp-tab">7D</span><span className="vp-tab">30D</span></div>
              </div>
              <div className="vp-overview-bars">
                {overviewBars.map((h, i) => (
                  <div key={i} className="vp-ov-bar-wrap">
                    <div className="vp-ov-bar" style={{height: `${h * 0.9}px`}} />
                  </div>
                ))}
              </div>
            </div>
            <div className="vp-card">
              <div className="vp-card-title" style={{marginBottom:10}}>Visitors by Time Period</div>
              <div className="vp-time-list">
                <div className="vp-time-row">Morning 30% <span>(38)</span></div>
                <div className="vp-time-row">Afternoon 45% <span>(58)</span></div>
                <div className="vp-time-row">Evening 25% <span>(32)</span></div>
              </div>
              <div className="vp-donut-wrap">
                <ResponsiveContainer width="100%" height={100}>
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={28} outerRadius={45} dataKey="value" stroke="none">
                      {pieData.map((e, i) => <Cell key={i} fill={e.color} />)}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="vp-donut-center">45%</div>
              </div>
            </div>
            <div className="vp-card">
              <div className="vp-card-title" style={{marginBottom:10}}>Visitors by Day</div>
              <ResponsiveContainer width="100%" height={130}>
                <BarChart data={barData} barSize={14} margin={{top:4,right:0,left:-28,bottom:0}}>
                  <XAxis dataKey="day" axisLine={false} tickLine={false} tick={{fontSize:10,fill:'#94a3b8'}} />
                  <YAxis axisLine={false} tickLine={false} tick={{fontSize:10,fill:'#94a3b8'}} />
                  <Tooltip cursor={{fill:'transparent'}} />
                  <Bar dataKey="v" fill="#8b5cf6" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Breakdown + Demographics */}
          <div className="vp-card">
            <div className="vp-two-col-inner">
              <div className="vp-breakdown">
                <div className="vp-card-title">Visitor Type Breakdown</div>
                <div className="vp-breakdown-row">New Visitors <strong>68% (87)</strong></div>
                <div className="vp-breakdown-row">Returning Visitors <strong>32% (41)</strong></div>
                <div className="vp-breakdown-bar-wrap">
                  <div className="vp-breakdown-bar" style={{width:'68%', background:'#6366f1'}} />
                  <div className="vp-breakdown-bar" style={{width:'32%', background:'#a5b4fc'}} />
                </div>
                <div className="vp-breakdown-sub">Returning visitor % — last 7 days</div>
              </div>
              <div className="vp-demographics">
                <div className="vp-card-title">Visitor Demographics</div>
                {[{label:'18-24',pct:72},{label:'25-34',pct:85},{label:'35-44',pct:60},{label:'45-54',pct:45},{label:'55+',pct:30}].map(d => (
                  <div className="vp-demo-row" key={d.label}>
                    <span className="vp-demo-label">{d.label}</span>
                    <div className="vp-demo-track"><div className="vp-demo-fill" style={{width:`${d.pct}%`}} /></div>
                  </div>
                ))}
                <div className="vp-demo-gender">Male 52% · Female 44% · Unknown 4%</div>
                <div className="vp-demo-note">AI estimated, not based on biometric data</div>
              </div>
            </div>
          </div>

          {/* Journey */}
          <div className="vp-card">
            <div className="vp-card-header">
              <span className="vp-card-title">Visitor Journey / Path Flow</span>
              <span className="vp-most-common">Most common path</span>
            </div>
            <div className="vp-journey-row">
              {journeySteps.map((step, i) => (
                <div key={step} className="vp-journey-step-wrap">
                  <div className="vp-journey-step">{step}</div>
                  {i < journeySteps.length - 1 && <ChevronRight size={18} className="vp-journey-arrow" />}
                </div>
              ))}
              <ChevronRight size={18} className="vp-journey-arrow" />
              <div className="vp-journey-path-tag">Entrance → Main Floor → Fitting Room → Billing → Exit</div>
            </div>
          </div>

          {/* Zone Heatmap + Segments */}
          <div className="vp-two-col">
            <div className="vp-card">
              <div className="vp-card-title" style={{marginBottom:12}}>Zone-wise Visitor Heatmap</div>
              <div className="vp-heatmap-grid">
                {heatZones.map(z => (
                  <div className="vp-heat-cell" key={z.label} style={{background: z.color}}>
                    {z.label} <strong>{z.count}</strong>
                  </div>
                ))}
              </div>
            </div>
            <div className="vp-card">
              <div className="vp-card-title" style={{marginBottom:12}}>Visitor Segments</div>
              {segments.map(s => (
                <div className="vp-segment-row" key={s.name}>
                  <span className="vp-seg-dot" style={{background: s.color}} />
                  <span className="vp-seg-name">{s.name}</span>
                  <span className="vp-seg-pct">{s.pct}%</span>
                </div>
              ))}
              <button className="vp-seg-link">View Segment Details →</button>
            </div>
          </div>

          {/* Funnel + Comparison */}
          <div className="vp-two-col">
            <div className="vp-card">
              <div className="vp-card-title" style={{marginBottom:12}}>Conversion Funnel</div>
              {funnelSteps.map(f => (
                <div className="vp-funnel-row" key={f.label}>
                  <span className="vp-funnel-label">{f.label} <strong>{f.count}</strong></span>
                  <div className="vp-funnel-track"><div className="vp-funnel-fill" style={{width:`${f.pct}%`}} /></div>
                </div>
              ))}
            </div>
            <div className="vp-card">
              <div className="vp-card-title">Visitor Comparison</div>
              <div className="vp-comp-sub">This Week vs Last Week</div>
              <div className="vp-comp-value">↑ 12% WoW</div>
              <div className="vp-comp-note">Store-to-store comparison ON</div>
            </div>
          </div>

          {/* Sessions Table from API */}
          {sessions.length > 0 && (
            <div className="vp-card">
              <div className="vp-card-header">
                <span className="vp-card-title">Today's Visitor Sessions</span>
                <span style={{ fontSize:11, color:'#6366f1', background:'#eff6ff',
                  border:'1px solid #bfdbfe', borderRadius:20, padding:'2px 10px' }}>
                  {sessions.length} sessions
                </span>
              </div>
              <div style={{ overflowX:'auto' }}>
                <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                  <thead>
                    <tr style={{ borderBottom:'1px solid #e5e7eb', background:'#f9fafb' }}>
                      {['Session Code','Entry','Exit','Duration','Zone','Employee','Status'].map(h => (
                        <th key={h} style={{ padding:'8px 12px', textAlign:'left', color:'#6b7280', fontWeight:600, fontSize:11 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(report?.records || sessions).map((r, i) => (
                      <tr key={i} style={{ borderBottom:'1px solid #f3f4f6' }}>
                        <td style={{ padding:'8px 12px', color:'#6366f1', fontWeight:600, fontFamily:'monospace' }}>{r.sessionCode || r.session_code}</td>
                        <td style={{ padding:'8px 12px' }}>{r.entryTime || '—'}</td>
                        <td style={{ padding:'8px 12px' }}>{r.exitTime  || '—'}</td>
                        <td style={{ padding:'8px 12px', fontWeight:600 }}>{r.duration || '—'}</td>
                        <td style={{ padding:'8px 12px' }}>{r.zone || '—'}</td>
                        <td style={{ padding:'8px 12px' }}>{r.assignedTo || '—'}</td>
                        <td style={{ padding:'8px 12px' }}>
                          <span style={{ fontSize:10, fontWeight:700, padding:'2px 8px', borderRadius:20,
                            background: r.status==='ACTIVE' ? '#f0fdf4' : '#eff6ff',
                            color: r.status==='ACTIVE' ? '#16a34a' : '#2563eb',
                            border: `1px solid ${r.status==='ACTIVE' ? '#bbf7d0' : '#bfdbfe'}` }}>
                            {r.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Forecast */}
          <div className="vp-card">
            <div className="vp-card-header">
              <span className="vp-card-title">Predictive Footfall Forecast</span>
              <span className="vp-next-badge">Next 7 Days</span>
            </div>
            <div className="vp-forecast-chart">
              <ResponsiveContainer width="100%" height={80}>
                <BarChart data={[{d:'Mon',v:90},{d:'Tue',v:110},{d:'Wed',v:130},{d:'Thu',v:120},{d:'Fri',v:160},{d:'Sat',v:180},{d:'Sun',v:140}]} barSize={18} margin={{top:4,right:0,left:-28,bottom:0}}>
                  <XAxis dataKey="d" axisLine={false} tickLine={false} tick={{fontSize:10,fill:'#94a3b8'}} />
                  <YAxis axisLine={false} tickLine={false} tick={{fontSize:10,fill:'#94a3b8'}} />
                  <Tooltip cursor={{fill:'transparent'}} />
                  <Bar dataKey="v" fill="#bbf7d0" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="vp-forecast-note">Expected 15% increase this weekend — consider extra staffing</div>
          </div>

          {/* Alerts */}
          <div className="vp-card">
            <div className="vp-card-title" style={{marginBottom:10}}>Alerts & Anomalies related to Visitors</div>
            <div className="vp-alerts-row">
              <span className="vp-alert-item blue"><span className="vp-alert-dot blue" />Unusual spike detected - 2:00 PM <span className="vp-alert-tag">Info</span></span>
              <span className="vp-alert-item orange"><span className="vp-alert-dot orange" />Visitor count below average - Tuesday <span className="vp-alert-tag orange">Warning</span></span>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};

export default Visitors;
