import React, { useEffect, useRef, useState } from 'react';
import { Menu, Store, ChevronDown, Calendar, Bell, CheckCheck, X, User, LogOut } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import '../Style/Header.css';

const Header = ({ title = "Dashboard", subtitle = "Overview of store performance and analytics" }) => {
  const navigate = useNavigate();
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [unread, setUnread] = useState(3);
  const notificationsRef = useRef(null);
  const profileRef = useRef(null);

  const user = (() => { try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; } })();
  const initials = [user.firstName, user.lastName].filter(Boolean).map(n => n[0]).join('').toUpperCase() || 'SA';
  const displayName = [user.firstName, user.lastName].filter(Boolean).join(' ') || 'Super Admin';

  useEffect(() => {
    const handler = (e) => {
      if (notificationsRef.current && !notificationsRef.current.contains(e.target)) setNotificationsOpen(false);
      if (profileRef.current && !profileRef.current.contains(e.target)) setProfileOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  return (
    <header className="dashboard-header">
      <div className="header-left">
        <button className="menu-btn"><Menu size={24} /></button>
        <div className="header-titles">
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
      </div>

      <div className="header-right">
        <div className="header-dropdown">
          <Store size={16} className="dropdown-icon" />
          <span>Store 1 - Fashion Store</span>
          <ChevronDown size={16} className="chevron" />
        </div>

        <div className="header-dropdown">
          <Calendar size={16} className="dropdown-icon" />
          <span>21 May 2025</span>
          <ChevronDown size={16} className="chevron" />
        </div>

        <div className="notifications-anchor" ref={notificationsRef}>
          <button className="notification-btn" onClick={() => setNotificationsOpen(o => !o)} aria-label="View notifications">
            <Bell size={20} />
            {unread > 0 && <span className="badge">{unread}</span>}
          </button>
          {notificationsOpen && (
            <div className="notifications-popover">
              <div className="notifications-title"><b>Notifications</b><button onClick={() => setUnread(0)}><CheckCheck size={14} /> Mark all read</button></div>
              <button className="notifications-close" onClick={() => setNotificationsOpen(false)}><X size={15} /></button>
              <div className="notification-row"><span className="notification-mark red" /><div><b>Camera CAM-07 is offline</b><small>12 minutes ago</small></div></div>
              <div className="notification-row"><span className="notification-mark orange" /><div><b>Queue length is high</b><small>20 minutes ago</small></div></div>
              <div className="notification-row"><span className="notification-mark green" /><div><b>Daily sales report is ready</b><small>1 hour ago</small></div></div>
            </div>
          )}
        </div>

        <div className="profile-anchor" ref={profileRef}>
          <div className="header-profile" onClick={() => setProfileOpen(o => !o)}>
            <div className="profile-avatar">{initials}</div>
            <div className="profile-info">
              <span className="profile-name">{displayName}</span>
              <span className="profile-role">Admin</span>
            </div>
            <ChevronDown size={14} style={{ color: '#94a3b8', marginLeft: 4 }} />
          </div>
          {profileOpen && (
            <div className="profile-dropdown">
              <div className="profile-dropdown-header">
                <div className="profile-dropdown-avatar">{initials}</div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14, color: '#111827' }}>{displayName}</div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>{user.email || 'superadmin@bachraj.com'}</div>
                </div>
              </div>
              <div className="profile-dropdown-divider" />
              <button className="profile-dropdown-item" onClick={() => { setProfileOpen(false); navigate('/settings'); }}>
                <User size={15} /> View Profile
              </button>
              <button className="profile-dropdown-item danger" onClick={handleLogout}>
                <LogOut size={15} /> Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;
