import { useState, useEffect } from 'react';
import { Camera, MapPin, Users, Share2, Clock, Pencil, CalendarDays, Download, MoreHorizontal, Trophy } from 'lucide-react';
import Sidebar from './Sidebar';
import Header from './Header';
import '../Style/StoreInfo.css';
import { getOrganizations, getStores, updateOrganization, createStore } from '../Services/StoreInfoservice';

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

const docs = [
  { name: 'Fire Safety Certificate', expiry: '12 Mar 2026', status: 'Valid' },
  { name: 'Trade License', expiry: '25 Jan 2026', status: 'Valid' },
  { name: 'CCTV Compliance Certificate', expiry: '10 Aug 2025', status: 'Expires Soon' },
  { name: 'Health & Safety Audit', expiry: '05 Dec 2025', status: 'Valid' },
  { name: 'Building NOC', expiry: '18 Nov 2026', status: 'Valid' },
];

const factors = [
  { label: 'Camera Uptime', value: 100 },
  { label: 'Staff Attendance', value: 85 },
  { label: 'Alert Response Time', value: 78 },
  { label: 'Compliance Status', value: 90 },
];

const configCards = [
  { label: 'Cameras', value: '12', sub: 'Active cameras', icon: Camera, color: 'blue' },
  { label: 'Zones', value: '6', sub: 'Configured zones', icon: MapPin, color: 'green' },
  { label: 'Employees', value: '24', sub: 'Active staff', icon: Users, color: 'blue' },
  { label: 'Integrations', value: '2', sub: 'POS, Slack', icon: Share2, color: 'purple' },
  { label: 'Working Hours', value: '09:00 AM - 09:00 PM', sub: 'Open today', icon: Clock, color: 'blue' },
];

const StoreInfo = () => {
  const [org, setOrg] = useState(null);
  const [stores, setStores] = useState([]);
  const [currentStore, setCurrentStore] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editMode, setEditMode] = useState(false);
  const [editForm, setEditForm] = useState({});
  const [showAddStore, setShowAddStore] = useState(false);
  const [newStore, setNewStore] = useState({ storeCode: '', name: '', city: '', state: '' });
  const [error, setError] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const orgsRes = await getOrganizations();
      const orgData = orgsRes.data?.[0] || null;
      setOrg(orgData);
      if (orgData) {
        const storesRes = await getStores(orgData.id);
        const storeList = storesRes.data || [];
        setStores(storeList);
        setCurrentStore(storeList[0] || null);
      }
    } catch (e) {
      setError('Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  async function handleUpdateOrg(e) {
    e.preventDefault();
    try {
      await updateOrganization(org.id, editForm);
      setOrg(prev => ({ ...prev, ...editForm }));
      setEditMode(false);
    } catch (e) {
      setError(e.response?.data?.message || 'Update failed');
    }
  }

  async function handleAddStore(e) {
    e.preventDefault();
    try {
      const res = await createStore({ ...newStore, organizationId: org.id });
      setStores(prev => [res.data, ...prev]);
      setShowAddStore(false);
      setNewStore({ storeCode: '', name: '', city: '', state: '' });
    } catch (e) {
      setError(e.response?.data?.message || 'Failed to create store');
    }
  }

  if (loading) return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="main-content-wrapper">
        <Header title="Store Information" subtitle="Manage store and configuration details" />
        <div className="si-scroll"><p style={{ color: '#6b7280', fontSize: 13 }}>Loading...</p></div>
      </div>
    </div>
  );

  return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="main-content-wrapper">
        <Header title="Store Information" subtitle="Manage store and configuration details" />
        <div className="si-scroll">

          {error && <p style={{ color: '#dc2626', fontSize: 12, margin: 0 }}>{error}</p>}

          {/* Store / Org Details */}
          <div className="si-card si-details-grid">
            <div className="si-photo-wrap">
              <img src="/assets/store-bg.png" alt="Store" />
              <button className="si-change-photo-btn"><Camera size={13} /> Change Photo</button>
            </div>
            {editMode ? (
              <form onSubmit={handleUpdateOrg} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[['name', 'Name'], ['email', 'Email'], ['country', 'Country'], ['timezone', 'Timezone']].map(([key, label]) => (
                  <div key={key} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <label style={{ fontSize: 12, color: '#6b7280', width: 80 }}>{label}</label>
                    <input
                      style={{ fontSize: 13, border: '1px solid #d1d5db', borderRadius: 5, padding: '3px 8px', flex: 1 }}
                      value={editForm[key] ?? ''}
                      onChange={e => setEditForm(p => ({ ...p, [key]: e.target.value }))}
                    />
                  </div>
                ))}
                <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                  <button type="submit" className="si-edit-btn" style={{ background: '#2563eb', color: '#fff', border: 'none' }}>Save</button>
                  <button type="button" className="si-outline-btn" onClick={() => setEditMode(false)}>Cancel</button>
                </div>
              </form>
            ) : (
              <div className="si-details-info">
                <dl>
                  <div><dt>Organization</dt><dd>{org?.name || '—'}</dd></div>
                  <div><dt>Store Name</dt><dd>{currentStore?.name || '—'}</dd></div>
                  <div><dt>Store Code</dt><dd>{currentStore?.store_code || '—'}</dd></div>
                  <div><dt>Address</dt><dd>{[currentStore?.address_line1, currentStore?.city, currentStore?.state, currentStore?.postal_code].filter(Boolean).join(', ') || '—'}</dd></div>
                  <div><dt>Email</dt><dd>{org?.email || '—'}</dd></div>
                  <div><dt>Timezone</dt><dd>{currentStore?.timezone || org?.timezone || '—'}</dd></div>
                  <div><dt>Status</dt><dd>
                    <span className={`si-pill ${currentStore?.status === 'ACTIVE' ? 'green' : 'gray'}`}>
                      <span className={`si-dot ${currentStore?.status === 'ACTIVE' ? 'green' : 'gray'}`} />
                      {currentStore?.status || '—'}
                    </span>
                  </dd></div>
                </dl>
              </div>
            )}
            {!editMode && (
              <button className="si-edit-btn" onClick={() => { setEditMode(true); setEditForm({ name: org?.name, email: org?.email, country: org?.country, timezone: org?.timezone }); }}>
                <Pencil size={13} /> Edit Details
              </button>
            )}
          </div>

          {/* Store Configuration */}
          <div className="si-card">
            <p className="si-title">Store Configuration</p>
            <div className="si-config-grid">
              {configCards.map(({ label, value, sub, icon: Icon, color }) => (
                <div className="si-config-card" key={label}>
                  <div className={`si-config-icon ${color}`}><Icon size={20} /></div>
                  <div className="si-config-top">{label}</div>
                  <div className="si-config-val">{value}</div>
                  <div className="si-config-sub">{sub}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Zone Map + Operating Hours */}
          <div className="si-two-col">
            <div className="si-card">
              <div className="si-row-between">
                <div>
                  <p className="si-title mb0">Zone Map</p>
                  <p className="si-sub">Click on a zone to view or edit details</p>
                </div>
                <button className="si-outline-btn">Edit Zones</button>
              </div>
              <div className="si-zone-map">
                <div className="si-zone green" style={{ top: '8%', left: '4%', width: '28%', height: '32%' }}>Fitting Room<br />(Z3)</div>
                <div className="si-zone purple" style={{ top: '8%', left: '35%', width: '30%', height: '32%' }}>Billing Counter<br />(Z4)</div>
                <div className="si-zone orange" style={{ top: '8%', left: '68%', width: '28%', height: '55%' }}>Checkout<br />(Z5)</div>
                <div className="si-zone blue" style={{ top: '43%', left: '4%', width: '60%', height: '35%' }}>Main Floor<br />(Z2)</div>
                <div className="si-zone lightblue" style={{ top: '80%', left: '20%', width: '40%', height: '16%' }}>Entrance<br />(Z1)</div>
              </div>
            </div>
            <div className="si-card">
              <p className="si-title">Operating Hours</p>
              <p className="si-sub">Set store operating hours for each day</p>
              <div className="si-hours-list">
                {days.map(day => (
                  <div className="si-hours-row" key={day}>
                    <span className="si-day">{day}</span>
                    <span className="si-time-box">09:00 AM</span>
                    <span className="si-dash">–</span>
                    <span className="si-time-box">09:00 PM</span>
                    <CalendarDays size={13} className="si-cal" />
                    <label className="si-check"><input type="checkbox" defaultChecked /><span>Open</span></label>
                  </div>
                ))}
              </div>
              <div className="si-holiday-bar">
                <div className="si-holiday-left">
                  <CalendarDays size={15} style={{ color: '#2563eb' }} />
                  <div>
                    <div className="si-holiday-title">Holiday Schedule</div>
                    <div className="si-holiday-sub">Set special hours for holidays and events</div>
                  </div>
                </div>
                <div className="si-holiday-right">
                  <div className="si-toggle" />
                  <button className="si-outline-btn">Manage Holidays</button>
                </div>
              </div>
            </div>
          </div>

          {/* Multi-Store Overview */}
          <div className="si-card">
            <div className="si-row-between">
              <div>
                <p className="si-title mb0">Multi-Store Overview</p>
                <p className="si-sub">Manage all stores under your account</p>
              </div>
              <button className="si-outline-btn" onClick={() => setShowAddStore(true)}>+ Add Store</button>
            </div>

            {showAddStore && (
              <form onSubmit={handleAddStore} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, padding: '10px', background: '#f9fafb', borderRadius: 7, border: '1px solid #e5e7eb' }}>
                {[['storeCode', 'Store Code*'], ['name', 'Name*'], ['city', 'City'], ['state', 'State']].map(([key, ph]) => (
                  <input key={key} required={ph.includes('*')} placeholder={ph} value={newStore[key]}
                    onChange={e => setNewStore(p => ({ ...p, [key]: e.target.value }))}
                    style={{ fontSize: 12, border: '1px solid #d1d5db', borderRadius: 5, padding: '5px 9px', width: 130 }} />
                ))}
                <button type="submit" className="si-edit-btn" style={{ background: '#2563eb', color: '#fff', border: 'none' }}>Create</button>
                <button type="button" className="si-outline-btn" onClick={() => setShowAddStore(false)}>Cancel</button>
              </form>
            )}

            <table className="si-table">
              <thead><tr><th>Store Name</th><th>Location</th><th>Status</th><th>Code</th><th>Action</th></tr></thead>
              <tbody>
                {stores.length === 0 && (
                  <tr><td colSpan={5} style={{ color: '#9ca3af', textAlign: 'center' }}>No stores found</td></tr>
                )}
                {stores.map(s => (
                  <tr key={s.id}>
                    <td>
                      <strong>{s.name}</strong>
                      {currentStore?.id === s.id && <span className="si-cur-tag">Current</span>}
                    </td>
                    <td>{[s.city, s.state].filter(Boolean).join(', ') || '—'}</td>
                    <td>
                      <span className={`si-pill small ${s.status === 'ACTIVE' ? 'green' : 'gray'}`}>
                        <span className={`si-dot ${s.status === 'ACTIVE' ? 'green' : 'gray'}`} />{s.status}
                      </span>
                    </td>
                    <td>{s.store_code}</td>
                    <td>
                      {currentStore?.id === s.id
                        ? <button className="si-cur-btn">Current Store</button>
                        : <button className="si-switch-btn" onClick={() => setCurrentStore(s)}>Switch to this store</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Layout + Compliance */}
          <div className="si-two-col">
            <div className="si-card">
              <div className="si-row-between">
                <div>
                  <p className="si-title mb0">Store Layout & Camera Placement</p>
                  <p className="si-sub">Camera locations and coverage areas</p>
                </div>
                <button className="si-outline-btn"><Pencil size={12} /> Edit Layout</button>
              </div>
              <div className="si-layout-map">
                <span className="si-cam" style={{ top: '12%', left: '10%' }}>CAM-01</span>
                <span className="si-cam" style={{ top: '12%', right: '10%' }}>CAM-02</span>
                <span className="si-cam" style={{ bottom: '12%', left: '10%' }}>CAM-03</span>
                <span className="si-cam" style={{ bottom: '12%', right: '10%' }}>CAM-04</span>
              </div>
            </div>
            <div className="si-card">
              <div className="si-row-between">
                <div>
                  <p className="si-title mb0">Compliance & Certifications</p>
                  <p className="si-sub">Manage important store documents</p>
                </div>
                <button className="si-outline-btn"><Download size={12} /> Upload Document</button>
              </div>
              <table className="si-table">
                <thead><tr><th>Document Name</th><th>Expiry Date</th><th>Status</th><th>Action</th></tr></thead>
                <tbody>
                  {docs.map(d => (
                    <tr key={d.name}>
                      <td>{d.name}</td>
                      <td>{d.expiry}</td>
                      <td><span className={`si-doc-badge ${d.status === 'Valid' ? 'valid' : 'expiring'}`}><span className={`si-dot ${d.status === 'Valid' ? 'green' : 'orange'}`} />{d.status}</span></td>
                      <td className="si-doc-actions"><Download size={13} /><MoreHorizontal size={13} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Health Score */}
          <div className="si-card">
            <p className="si-title">Store Health Score</p>
            <div className="si-health-grid">
              <div className="si-score-wrap">
                <div className="si-arc-wrap">
                  <svg viewBox="0 0 120 70">
                    <path d="M10,60 A50,50 0 0,1 110,60" fill="none" stroke="#e5e7eb" strokeWidth="10" strokeLinecap="round" />
                    <path d="M10,60 A50,50 0 0,1 110,60" fill="none" stroke="#22c55e" strokeWidth="10" strokeLinecap="round" strokeDasharray="157" strokeDashoffset="31" />
                  </svg>
                  <div className="si-arc-label">
                    <span className="si-score-num">88</span><span className="si-score-of"> / 100</span>
                    <span className="si-score-grade">Excellent</span>
                  </div>
                </div>
                <p className="si-score-sub">Store is performing well</p>
              </div>
              <div className="si-factors">
                <p className="si-factors-title">Contributing Factors</p>
                {factors.map(f => (
                  <div className="si-factor-row" key={f.label}>
                    <span className="si-factor-lbl">{f.label}</span>
                    <div className="si-bar"><div className="si-bar-fill" style={{ width: `${f.value}%` }} /></div>
                    <span className="si-factor-pct">{f.value}%</span>
                  </div>
                ))}
              </div>
              <div className="si-health-badge">
                <Trophy size={34} className="si-trophy" />
                <p><strong>Your store is performing well!</strong><br />Keep up the good work. All critical systems are operational.</p>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};

export default StoreInfo;
