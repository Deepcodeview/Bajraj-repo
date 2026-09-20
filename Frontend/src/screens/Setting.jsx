import { useState, useEffect } from 'react';
import { Bell, Boxes, BriefcaseBusiness, CreditCard, Download, KeyRound, LockKeyhole, Mail, Plus, Save, ShieldCheck, Smartphone, UserRound, UsersRound, Webhook, X } from 'lucide-react';
import Sidebar from './Sidebar';
import Header from './Header';
import { getMe } from '../Services/Settingservice';
import { getOrganizations, updateOrganization } from '../Services/StoreInfoservice';
import { useToast } from '../components/Toast';
import '../Style/Setting.css';

const Toggle = ({ initial = true }) => { const [on, setOn] = useState(initial); return <button onClick={() => setOn(!on)} className={`set-toggle ${on ? 'on' : ''}`}><i /></button>; };
const Card = ({ title, subtitle, action, children, cls = '' }) => <section className={`set-card ${cls}`}><header><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</header>{children}</section>;
const Btn = ({ children, ghost = false, icon: Icon, onClick, disabled }) => <button className={`set-btn ${ghost ? 'ghost' : ''}`} onClick={onClick} disabled={disabled}>{Icon && <Icon size={14} />} {children}</button>;

const prefs = [['Email Alerts', 'Receive important alerts via email', Mail, true], ['SMS Alerts', 'Receive critical alerts via SMS', Smartphone, true], ['Push Notifications', 'Get instant notifications in mobile app', Bell, true], ['Daily Digest', 'Receive daily summary report', BriefcaseBusiness, true], ['Critical-only Mode', 'Only receive critical alerts', Bell, false]];

export default function Setting() {
  const toast = useToast();
  const [section, setSection] = useState('Profile');
  const [profile, setProfile] = useState({ fullName: '', email: '', phone: '', role: '' });
  const [org, setOrg] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const stored = (() => { try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; } })();
    setProfile({
      fullName: [stored.firstName, stored.lastName].filter(Boolean).join(' ') || '',
      email: stored.email || '',
      phone: stored.phone || '',
      role: stored.role || 'SUPER_ADMIN',
    });
    getOrganizations().then(r => setOrg(r.data?.[0] || null)).catch(() => {});
  }, []);

  const handleSaveProfile = async () => {
    if (!org) { toast('No organization found', 'error'); return; }
    setSaving(true);
    try {
      const [first, ...rest] = profile.fullName.trim().split(' ');
      await updateOrganization(org.id, { name: org.name });
      const stored = (() => { try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; } })();
      localStorage.setItem('user', JSON.stringify({ ...stored, firstName: first, lastName: rest.join(' ') || stored.lastName }));
      toast('Profile saved successfully');
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="main-content-wrapper">
        <Header title="Settings" subtitle="Manage account, team and system preferences" />
        <main className="set-scroll">
          <aside className="set-nav">
            {[['Profile', UserRound], ['Team & Roles', UsersRound], ['Notifications', Bell], ['Billing & Plan', CreditCard], ['Integrations', Boxes], ['Security', ShieldCheck], ['API Keys', KeyRound]].map(([x, I]) => (
              <button onClick={() => setSection(x)} className={section === x ? 'active' : ''} key={x}><I size={16} />{x}</button>
            ))}
          </aside>
          <div className="set-content">

            <Card title="Profile" subtitle="Manage your personal information and account details" cls="set-profile">
              <div className="set-avatar"><b>{profile.fullName.split(' ').map(n => n[0]).join('').toUpperCase() || 'SA'}</b><span>Click to upload<br />JPG, PNG (Max 2MB)</span></div>
              <div className="set-form">
                <label>Full Name<input value={profile.fullName} onChange={e => setProfile(p => ({ ...p, fullName: e.target.value }))} /></label>
                <label>Email Address<input value={profile.email} onChange={e => setProfile(p => ({ ...p, email: e.target.value }))} /></label>
                <label>Phone Number<input value={profile.phone} onChange={e => setProfile(p => ({ ...p, phone: e.target.value }))} /></label>
                <label>Role<select value={profile.role} onChange={e => setProfile(p => ({ ...p, role: e.target.value }))}><option value="SUPER_ADMIN">Super Admin</option><option value="ADMIN">Manager</option></select></label>
                <div><Btn icon={Save} onClick={handleSaveProfile} disabled={saving}>{saving ? 'Saving...' : 'Save Changes'}</Btn></div>
              </div>
            </Card>

            <div className="set-two">
              <Card title="Team & Roles" subtitle="Manage team members and their roles" action={<Btn ghost icon={Plus}>Invite Member</Btn>}>
                <table className="set-table"><thead><tr><th>Member</th><th>Email</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead>
                  <tbody>{[['Shubham Chaudhari', 'admin@bachhraj.com', 'Admin', 'Active'], ['Rahul Kumar', 'rahul@bachhraj.com', 'Manager', 'Active'], ['Priya Sharma', 'priya@bachhraj.com', 'Manager', 'Active'], ['Amit Mehta', 'amit@bachhraj.com', 'Viewer', 'Active'], ['Sneha Nair', 'sneha@bachhraj.com', 'Viewer', 'Invited']].map(x => (
                    <tr key={x[0]}><td><i className="set-initial">{x[0].split(' ').map(a => a[0]).join('')}</i>{x[0]}</td><td>{x[1]}</td><td><span className="set-role">{x[2]}</span></td><td><span className={`set-tag ${x[3] === 'Invited' ? 'orange' : ''}`}>{x[3]}</span></td><td>•••</td></tr>
                  ))}</tbody>
                </table>
              </Card>
              <Card title="Notification Preferences" subtitle="Configure how you want to receive notifications">
                <div className="set-prefs">{prefs.map(([n, d, I, on]) => (
                  <div key={n}><span className={n === 'Critical-only Mode' ? 'red-icon' : ''}><I size={17} /></span><label><b>{n}</b><small>{d}</small></label><Toggle initial={on} /></div>
                ))}</div>
              </Card>
            </div>

            <Card title="Billing & Plan" subtitle="Manage your subscription and billing details">
              <div className="set-billing">
                <div className="set-plan"><span>♛</span><div><b>Pro Plan<br /><strong>₹24,999</strong> / month</b><small>Advanced analytics, multi-store support, priority support</small></div><Btn>Upgrade Plan</Btn></div>
                <div className="set-usage">{[['Camera Usage', '12 / 15', 70], ['Employee Seats', '24 / 50', 48], ['Storage Used', '120 GB / 500 GB', 30]].map(x => (
                  <div key={x[0]}><label>{x[0]} <b>{x[1]}</b></label><i><em style={{ width: `${x[2]}%` }} /></i></div>
                ))}</div>
                <div className="set-payment"><b>Payment Method</b><span>VISA &nbsp; •••• 4242<br /><small>Expires 12/2026</small></span><Btn ghost>Update</Btn></div>
              </div>
              <h3 className="set-mini-title">Invoice History <a>View All Invoices</a></h3>
              <table className="set-table"><thead><tr><th>Invoice #</th><th>Date</th><th>Amount</th><th>Status</th><th>Download</th></tr></thead>
                <tbody>{['INV-2025-05', 'INV-2025-04', 'INV-2025-03'].map((x, i) => (
                  <tr key={x}><td>{x}</td><td>0{i + 1} May 2025</td><td>₹24,999</td><td><span className="set-tag">Paid</span></td><td><Download size={14} color="#4f46e5" /></td></tr>
                ))}</tbody>
              </table>
            </Card>

            <div className="set-two">
              <Card title="Integrations" subtitle="Connect with your existing tools and systems">
                <div className="set-integrations">{[['POS System', 'Connected'], ['HR / ERP', 'Connected'], ['Slack', 'Connected'], ['WhatsApp Business', 'Connect'], ['Google Sheets', 'Connected']].map(([x, y], i) => (
                  <div key={x}><span>{['▣', '▤', '✣', '●', '▦'][i]}</span><b>{x}</b><small className={y === 'Connect' ? 'neutral' : ''}>{y}</small><Btn ghost>{y === 'Connect' ? 'Connect' : 'Configure'}</Btn></div>
                ))}</div>
              </Card>
              <Card title="Security" subtitle="Manage your account security settings">
                <div className="set-security-toggle"><LockKeyhole size={17} /><span><b>Two-Factor Authentication (2FA)</b><small>Add an extra layer of security to your account</small></span><Toggle /></div>
                <h3 className="set-mini-title">Active Sessions <a>View All</a></h3>
                <table className="set-table"><thead><tr><th>Device</th><th>Location</th><th>Last Active</th><th>Action</th></tr></thead>
                  <tbody>{[['MacBook Pro (Chrome)', 'Mumbai, India', '21 May 2025, 10:24 AM'], ['iPhone (Mobile App)', 'Mumbai, India', '21 May 2025, 09:12 AM'], ['Windows (Edge)', 'Pune, India', '20 May 2025, 06:45 PM']].map(x => (
                    <tr key={x[0]}>{x.map(y => <td key={y}>{y}</td>)}<td><a>Log out ›</a></td></tr>
                  ))}</tbody>
                </table>
                <div className="set-security-actions"><Btn ghost icon={KeyRound}>Change Password</Btn><Btn ghost icon={Download}>View Audit Log</Btn></div>
              </Card>
            </div>

            <Card title="API Keys & Webhooks" subtitle="Manage API keys for external integrations and webhooks for real-time data">
              <div className="set-api">
                <div><h3>API Keys <Btn ghost icon={Plus}>Generate New Key</Btn></h3>
                  <table className="set-table"><thead><tr><th>Name</th><th>Key</th><th>Created At</th><th>Last Used</th><th>Status</th><th>Action</th></tr></thead>
                    <tbody>{[['Production Key', 'sk_live_••••••••••••••••', '10 Jan 2025', '21 May 2025'], ['Development Key', 'sk_test_••••••••••••••••', '15 Feb 2025', '18 May 2025'], ['Analytics Key', 'sk_anal_••••••••••••••••', '01 Mar 2025', '15 May 2025']].map(x => (
                      <tr key={x[0]}>{x.map(y => <td key={y}>{y}</td>)}<td><span className="set-tag">Active</span></td><td><a className="set-revoke">Revoke</a></td></tr>
                    ))}</tbody>
                  </table>
                </div>
                <div className="set-webhook">
                  <h3>Webhook Configuration</h3>
                  <label>Webhook URL<input defaultValue="https://yourdomain.com/api/webhook" /></label>
                  <Btn ghost>Test</Btn>
                  <p>Events to Send</p>
                  <div className="set-checks">{['Alerts', 'Transactions', 'Attendance', 'System Logs'].map((x, i) => (
                    <label key={x}><input type="checkbox" defaultChecked={i < 3} />{x}</label>
                  ))}</div>
                  <Btn icon={Webhook}>Save Webhook</Btn>
                </div>
              </div>
            </Card>

          </div>
        </main>
      </div>
    </div>
  );
}
