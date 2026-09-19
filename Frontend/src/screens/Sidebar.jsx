import { 
  Store, 
  Home, 
  ScanFace, 
  Users, 
  Receipt, 
  UserCog, 
  Bell, 
  BarChart2, 
  Settings,
  MoreVertical,
  Video,
  Bot,
  Sparkles,
  LogOut
} from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import '../Style/Sidebar.css';

const Sidebar = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const isActive = (path) => location.pathname === path;

  return (
    <aside className="dashboard-sidebar">
      <div className="sidebar-brand">
        <div className="brand-logo-container">
          <Store size={22} className="brand-logo-icon" />
        </div>
        <div className="brand-text">
          <span className="brand-name">Bachhraj</span>
          <span className="brand-sub">Smart Retail</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <a 
          href="#dashboard" 
          className={`nav-item ${isActive('/dashboard') ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); navigate('/dashboard'); }}
        >
          <Home size={18} />
          <span>Dashboard</span>
        </a>
        <a 
          href="#livedetection" 
          className={`nav-item ${isActive('/livedetection') ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); navigate('/livedetection'); }}
        >
          <ScanFace size={18} />
          <span>Live Detection</span>
        </a>
        <a 
          href="#visitors" 
          className={`nav-item ${isActive('/visitors') ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); navigate('/visitors'); }}
        >
          <Users size={18} />
          <span>Visitors</span>
        </a>
        <a href="#transactions" className={`nav-item ${isActive('/transactions') ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); navigate('/transactions'); }}>
          <Receipt size={18} />
          <span>Transactions</span>
        </a>
        <a href="#employees" className={`nav-item ${isActive('/employees') ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); navigate('/employees'); }}>
          <UserCog size={18} />
          <span>Employees</span>
        </a>
        <a href="#attendance" className={`nav-item ${isActive('/attendance') ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); navigate('/attendance'); }}>
          <Users size={18} />
          <span>Attendance</span>
        </a>
        <a
          href="#alerts"
          className={`nav-item ${isActive('/alerts') ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); navigate('/alerts'); }}
        >
          <Bell size={18} />
          <span>Alerts</span>
        </a>
        <a href="#reports" className={`nav-item ${isActive('/reports') ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); navigate('/reports'); }}>
          <BarChart2 size={18} />
          <span>Reports</span>
        </a>
        <a href="#camera-management" className={`nav-item ${isActive('/camera-management') ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); navigate('/camera-management'); }}>
          <Video size={18} />
          <span>Camera Management</span>
        </a>
        <a href="#ai-configuration" className={`nav-item ${isActive('/ai-configuration') ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); navigate('/ai-configuration'); }}>
          <Bot size={18} />
          <span>AI Configuration</span>
        </a>
        <a href="#retail-intelligence" className={`nav-item ${isActive('/retail-intelligence') ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); navigate('/retail-intelligence'); }}>
          <Sparkles size={18} />
          <span>Retail Intelligence</span>
        </a>
        <a
          href="#storeinfo"
          className={`nav-item ${isActive('/storeinfo') ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); navigate('/storeinfo'); }}
        >
          <Store size={18} />
          <span>Store Info</span>
        </a>
        <a href="#settings" className={`nav-item ${isActive('/settings') ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); navigate('/settings'); }}>
          <Settings size={18} />
          <span>Settings</span>
        </a>
      </nav>

      <div className="sidebar-bottom">
        <div className="admin-profile-widget">
          <div className="admin-avatar">SA</div>
          <div className="admin-info">
            <span className="admin-name">Super Admin</span>
            <span className="admin-email">superadmin@store.com</span>
          </div>
          <MoreVertical size={16} className="more-icon" />
        </div>
        <button
          className="logout-btn"
          onClick={() => {
            localStorage.removeItem('token');
            navigate('/login');
          }}
        >
          <LogOut size={16} />
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
