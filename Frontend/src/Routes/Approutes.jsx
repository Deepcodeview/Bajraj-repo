import { Routes, Route, Navigate } from 'react-router-dom';
import Login from '../screens/login';
import Dashboard from '../screens/dashboard';
import LiveDetection from '../screens/livedetection';
import Visitors from '../screens/Visitors';
import StoreInfo from '../screens/StoreInfo';
import Alerts from '../screens/Alerts';
import AnalyticsScreen from '../screens/AnalyticsScreen';
import Transaction from '../screens/Transaction';
import Setting from '../screens/Setting';
import Employees from '../screens/Employees';
import Attendance from '../screens/Attendance';
import Reports from '../screens/Reports';
import CameraManagement from '../screens/CameraManagement';

const Approutes = () => {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<Login />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/livedetection" element={<LiveDetection />} />
      <Route path="/visitors" element={<Visitors />} />
      <Route path="/storeinfo" element={<StoreInfo />} />
      <Route path="/alerts" element={<Alerts />} />
      <Route path="/transactions" element={<Transaction />} />
      <Route path="/camera-management" element={<CameraManagement />} />
      <Route path="/ai-configuration" element={<AnalyticsScreen type="ai" />} />
      <Route path="/retail-intelligence" element={<AnalyticsScreen type="intelligence" />} />
      <Route path="/employees" element={<Employees />} />
      <Route path="/attendance" element={<Attendance />} />
      <Route path="/reports" element={<Reports />} />
      <Route path="/settings" element={<Setting />} />
    </Routes>
  );
};

export default Approutes;
