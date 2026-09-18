import React, { useEffect, useRef, useState } from 'react';
import { Menu, Store, ChevronDown, Calendar, Bell, CheckCheck, X } from 'lucide-react';
import '../Style/Header.css';

const Header = ({ title = "Dashboard", subtitle = "Overview of store performance and analytics" }) => {
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [unread, setUnread] = useState(3);
  const notificationsRef = useRef(null);

  useEffect(() => {
    const closeOnOutsideClick = (event) => {
      if (notificationsRef.current && !notificationsRef.current.contains(event.target)) setNotificationsOpen(false);
    };
    document.addEventListener('mousedown', closeOnOutsideClick);
    return () => document.removeEventListener('mousedown', closeOnOutsideClick);
  }, []);
  return (
    <header className="dashboard-header">
      <div className="header-left">
        <button className="menu-btn">
          <Menu size={24} />
        </button>
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
          <button className="notification-btn" onClick={() => setNotificationsOpen(open => !open)} aria-label="View notifications">
            <Bell size={20} />
            {unread > 0 && <span className="badge">{unread}</span>}
          </button>
          {notificationsOpen && <div className="notifications-popover">
          <div className="notifications-title"><b>Notifications</b><button onClick={() => setUnread(0)}><CheckCheck size={14} /> Mark all read</button></div>
          <button className="notifications-close" onClick={() => setNotificationsOpen(false)} aria-label="Close notifications"><X size={15}/></button>
          <div className="notification-row"><span className="notification-mark red"/><div><b>Camera CAM-07 is offline</b><small>12 minutes ago</small></div></div>
          <div className="notification-row"><span className="notification-mark orange"/><div><b>Queue length is high</b><small>20 minutes ago</small></div></div>
          <div className="notification-row"><span className="notification-mark green"/><div><b>Daily sales report is ready</b><small>1 hour ago</small></div></div>
          </div>}
        </div>

        <div className="header-profile">
          <div className="profile-avatar">SA</div>
          <div className="profile-info">
            <span className="profile-name">Super Admin</span>
            <span className="profile-role">Admin</span>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
