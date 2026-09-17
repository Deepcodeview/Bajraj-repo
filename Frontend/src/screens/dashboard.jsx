import { useState, useEffect } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import { ArrowUpRight, Plus, AlertCircle, FileText, UserPlus, Settings } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, PieChart, Pie, Cell } from 'recharts';
import { CAMERAS, getJobStreamUrl } from '../Services/Livedetectionservice';
import '../Style/dashboard.css';

const barData = [
  {t:'12 AM',v:5},{t:'',v:8},{t:'',v:12},{t:'6 AM',v:20},{t:'',v:35},{t:'',v:50},
  {t:'12 PM',v:70},{t:'',v:60},{t:'',v:45},{t:'6 PM',v:30},{t:'',v:18},{t:'11 PM',v:8},
];
const salesData = [
  {d:'',v:60},{d:'',v:80},{d:'',v:70},{d:'',v:90},{d:'',v:110},{d:'',v:130},{d:'',v:160},
];
const pieData = [
  { name: 'Morning',   value: 38, color: '#6366f1' },
  { name: 'Afternoon', value: 58, color: '#22c55e' },
  { name: 'Evening',   value: 32, color: '#f97316' },
];
const summaryRows = [
  { label: 'Total Entries',    value: '128',     trend: '↑ 18.7%', trendColor: 'green' },
  { label: 'Exits',            value: '116',     trend: '↓ 12.4%', trendColor: 'red' },
  { label: 'Inside Now',       value: '12',      trend: '',         trendColor: '' },
  { label: 'Peak Time',        value: '3:00 PM', trend: '',         trendColor: '' },
  { label: 'Conversion Rate',  value: '24%',     trend: '',         trendColor: '' },
  { label: 'Avg. Basket Value',value: '₹973',    trend: '',         trendColor: '' },
];
const cameras = [
  { id: 'CAM-01', count: 12, status: 'ONLINE',  online: true },
  { id: 'CAM-02', count: 8,  status: 'ONLINE',  online: true },
  { id: 'CAM-03', count: 21, status: 'OFFLINE', online: false },
  { id: 'CAM-04', count: 5,  status: 'ONLINE',  online: true },
];
const alerts = [
  { dot: '#f97316', title: 'Crowd density',   level: 'High',     time: '2 min' },
  { dot: '#ef4444', title: 'Camera offline',  level: 'Critical', time: '8 min' },
  { dot: '#f97316', title: 'Long dwell time', level: 'Medium',   time: '14 min' },
];
const zonePerf = [
  { name: 'Entrance',        pct: 32 },
  { name: 'Main Floor',      pct: 28 },
  { name: 'Fitting Room',    pct: 18 },
  { name: 'Billing Counter', pct: 14 },
  { name: 'Checkout',        pct: 8  },
];
const quickActions = [
  { icon: Plus,        label: 'Add Camera' },
  { icon: AlertCircle, label: 'Create Alert Rule' },
  { icon: FileText,    label: 'Generate Report' },
  { icon: UserPlus,    label: 'Invite Team Member' },
  { icon: Settings,    label: 'View Store Settings' },
];

const Dashboard = () => {
  const [jobMap, setJobMap] = useState(() => {
    try { return JSON.parse(localStorage.getItem('ldJobMap') || '{}'); } catch { return {}; }
  });

  // Refresh jobMap every 5s from localStorage
  useEffect(() => {
    const t = setInterval(() => {
      try { setJobMap(JSON.parse(localStorage.getItem('ldJobMap') || '{}')); } catch {}
    }, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="main-content-wrapper">
        <Header title="Dashboard" subtitle="Overview of store performance and analytics" />
        <div className="db-scroll">

        {/* Stat Cards */}
        <div className="db-stats-row">
          {[
            { icon: '🔔', bg: '#6366f1', label: 'Total Visitors Today', value: '128',       trend: '↑ 18.7%' },
            { icon: '●',  bg: '#22c55e', label: 'Live Visitors',         value: '12',        trend: '+ Live' },
            { icon: '⏱',  bg: '#6366f1', label: 'Avg. Visit Duration',   value: '18m 24s',   trend: '↑ 6.3%' },
            { icon: '₹',  bg: '#22c55e', label: 'Total Sales Today',     value: '₹1,24,560', trend: '↑ 14.6%' },
          ].map(s => (
            <div className="db-stat-card" key={s.label}>
              <div className="db-stat-top">
                <div className="db-stat-icon" style={{background: s.bg}}>{s.icon}</div>
                <div className="db-stat-info">
                  <div className="db-stat-label">{s.label}</div>
                  <div className="db-stat-value">{s.value}</div>
                </div>
              </div>
              <div className="db-stat-bottom">
                <span className="db-stat-trend green">{s.trend}</span>
                <div className="db-sparkline">
                  {[3,5,4,6,5,7,6,8,7].map((h,i) => <div key={i} className="db-spark-bar" style={{height: h*4}} />)}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Row 2 */}
        <div className="db-row3">
          <div className="db-card">
            <div className="db-card-header">
              <div>
                <div className="db-card-title">Live People Count</div>
                <div className="db-card-sub">Real-time visitor movement throughout the day</div>
              </div>
              <div className="db-live-badge"><span className="db-dot green" />Live</div>
            </div>
            <div className="db-tabs">
              <span className="db-tab active">Today</span>
              <span className="db-tab">7D</span>
              <span className="db-tab">30D</span>
            </div>
            <div style={{height:180, marginTop:8}}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData} barSize={14} margin={{top:4,right:0,left:-28,bottom:0}}>
                  <XAxis dataKey="t" axisLine={false} tickLine={false} tick={{fontSize:10,fill:'#94a3b8'}} />
                  <YAxis axisLine={false} tickLine={false} tick={{fontSize:10,fill:'#94a3b8'}} />
                  <Tooltip cursor={{fill:'rgba(99,102,241,0.08)'}} />
                  <Bar dataKey="v" fill="#c7d2fe" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="db-card">
            <div className="db-card-title" style={{marginBottom:8}}>Visitors by Time Period</div>
            <div className="db-card-sub" style={{marginBottom:12}}>Distribution of visits today</div>
            <div className="db-pie-row">
              <div className="db-pie-legend">
                {pieData.map(p => (
                  <div className="db-pie-leg-item" key={p.name}>
                    <span className="db-dot" style={{background:p.color}} />
                    <span className="db-leg-name">{p.name}</span>
                    <span className="db-leg-pct">{p.value}%</span>
                  </div>
                ))}
              </div>
              <div className="db-donut-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={45} outerRadius={68} dataKey="value" stroke="none">
                      {pieData.map((e,i) => <Cell key={i} fill={e.color} />)}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="db-donut-center"><div className="db-donut-num">128</div><div className="db-donut-lbl">Visitors</div></div>
              </div>
            </div>
            <div className="db-compare-row">
              <span className="db-compare-text">Compare to last week</span>
              <div className="db-toggle" />
            </div>
          </div>

          <div className="db-card">
            <div className="db-card-title" style={{marginBottom:2}}>Today's Summary</div>
            <div className="db-card-sub" style={{marginBottom:12}}>Key store metrics</div>
            {summaryRows.map(r => (
              <div className="db-summary-row" key={r.label}>
                <span className="db-summary-label">{r.label}</span>
                <span className="db-summary-val">{r.value}</span>
                {r.trend && <span className={`db-summary-trend ${r.trendColor}`}>{r.trend}</span>}
              </div>
            ))}
          </div>
        </div>

        {/* Row 3 */}
        <div className="db-row3">
          <div className="db-card">
            <div className="db-card-header">
              <div>
                <div className="db-card-title">Live Camera Overview</div>
                <div className="db-card-sub">{CAMERAS.length} cameras • {Object.keys(jobMap).length} live</div>
              </div>
              <a href="/livedetection" className="db-link">View All Cameras →</a>
            </div>
            <div className="db-cam-grid">
              {CAMERAS.map(c => {
                const jobId = jobMap[c.id];
                const isLive = !!jobId;
                return (
                  <div className="db-cam-cell" key={c.id}>
                    <div className="db-cam-feed" style={{ position: 'relative', overflow: 'hidden', background: '#0f172a' }}>
                      {isLive ? (
                        <img src={getJobStreamUrl(jobId)} alt={c.name}
                          style={{ position:'absolute', inset:0, width:'100%', height:'100%', objectFit:'cover' }}
                          onError={e => { e.target.style.display = 'none'; }}/>
                      ) : null}
                      <span className="db-cam-id" style={{ position:'relative', zIndex:1 }}>{c.name}</span>
                      {!isLive && <span className="db-cam-count" style={{ position:'relative', zIndex:1 }}>—</span>}
                    </div>
                    <div className={`db-cam-status ${isLive ? 'online' : 'offline'}`}>
                      <span className={`db-dot ${isLive ? 'green' : 'red'}`}/>
                      {isLive ? 'LIVE' : 'OFFLINE'}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="db-card">
            <div className="db-card-header">
              <div className="db-card-title">Recent Alerts</div>
              <a href="#" className="db-link">View All →</a>
            </div>
            <div className="db-card-sub" style={{marginBottom:12}}>Latest AI events</div>
            {alerts.map((a,i) => (
              <div className="db-alert-row" key={i}>
                <span className="db-alert-dot" style={{background:a.dot}} />
                <div className="db-alert-info">
                  <div className="db-alert-title">{a.title}</div>
                  <div className={`db-alert-level ${a.level.toLowerCase()}`}>{a.level}</div>
                </div>
                <span className="db-alert-time">{a.time}</span>
              </div>
            ))}
          </div>

          <div className="db-card">
            <div className="db-card-title">Today's Sales</div>
            <div className="db-card-sub">Last 7 days</div>
            <div className="db-sales-val">₹1,24,560</div>
            <div className="db-sales-trend">↑ 14.6% vs yesterday</div>
            <div style={{height:100, marginTop:8}}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={salesData} barSize={18} margin={{top:4,right:0,left:-28,bottom:0}}>
                  <Bar dataKey="v" radius={[3,3,0,0]}>
                    {salesData.map((_,i) => <Cell key={i} fill={i === salesData.length-1 ? '#6366f1' : '#c7d2fe'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Row 4 */}
        <div className="db-row2">
          <div className="db-card">
            <div className="db-card-title" style={{marginBottom:4}}>Zone Performance</div>
            <div className="db-card-sub" style={{marginBottom:14}}>Footfall share by store zone</div>
            {zonePerf.map(z => (
              <div className="db-zone-row" key={z.name}>
                <span className="db-zone-name">{z.name}</span>
                <span className="db-zone-pct">{z.pct}%</span>
                <div className="db-zone-track"><div className="db-zone-fill" style={{width:`${z.pct*2.5}%`}} /></div>
              </div>
            ))}
          </div>
          <div className="db-card">
            <div className="db-card-title" style={{marginBottom:4}}>Employee Attendance Snapshot</div>
            <div className="db-card-sub" style={{marginBottom:12}}>Live workforce overview</div>
            <div className="db-emp-row">
              <div>
                <div className="db-emp-count">22 / 24</div>
                <div className="db-emp-label">Present Today</div>
                <div className="db-emp-break">On Break &nbsp;<strong>2</strong></div>
                <a href="#" className="db-link" style={{marginTop:16,display:'block'}}>View Employees →</a>
              </div>
              <div className="db-emp-circle">
                <svg viewBox="0 0 80 80" className="db-emp-svg">
                  <circle cx="40" cy="40" r="32" fill="none" stroke="#e5e7eb" strokeWidth="8"/>
                  <circle cx="40" cy="40" r="32" fill="none" stroke="#6366f1" strokeWidth="8"
                    strokeDasharray="201" strokeDashoffset="24" strokeLinecap="round"
                    transform="rotate(-90 40 40)"/>
                </svg>
                <div className="db-emp-pct">92%<br/><span>Attendance</span></div>
              </div>
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="db-card">
          <div className="db-card-title" style={{marginBottom:14}}>Quick Actions</div>
          <div className="db-quick-row">
            {quickActions.map(a => (
              <button className="db-quick-btn" key={a.label}>
                <a.icon size={16} className="db-quick-icon" />
                <span>{a.label}</span>
              </button>
            ))}
          </div>
        </div>

        </div>
      </div>
    </div>
  );
};

export default Dashboard;
