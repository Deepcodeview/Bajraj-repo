import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mail, Lock, Eye, EyeOff, Users, User, ArrowRightToLine, ArrowLeftFromLine, ScanFace, BarChart3, ShieldCheck, Monitor, Store } from 'lucide-react';
import { loginAPI } from '../Services/loginservice';
import '../Style/login.css';

const Login = () => {
  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const data = await loginAPI(email, password);
      
      if (data.success) {
        // Save the token and user data in local storage
        localStorage.setItem('token', data.data.token);
        localStorage.setItem('user', JSON.stringify(data.data.user));
        
        // Navigate to dashboard
        navigate('/dashboard');
      } else {
        setError(data.message || 'Login failed');
      }
    } catch (err) {
      setError(err.message || 'An error occurred during login. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrapper">
      <div className="login-background">
        <div className="login-overlay"></div>
      </div>
      
      <div className="login-content">
        {/* Left Side */}
        <div className="login-left-panel">
          <div className="brand-top-left">
            <div className="brand-logo-container">
              <Store className="brand-logo-icon" size={24} />
            </div>
            <div className="brand-text-col">
              <span className="brand-name">Bachhraj</span>
              <span className="brand-sub">Smart Retail</span>
            </div>
          </div>

          <div className="hero-text-section">
            <h1 className="hero-title">Smart Vision.<br/><span className="highlight-blue">Smarter Retail.</span></h1>
            <p className="hero-subtitle">
              AI-powered platform to monitor store operations,<br/>
              analyze visitor behavior and drive excellence.
            </p>
          </div>

          <div className="stats-grid">
            <div className="stat-box">
              <div className="stat-icon-wrapper bg-blue-10">
                <Users className="text-blue" size={22} />
              </div>
              <div className="stat-details">
                <span className="stat-label">Visitors Today</span>
                <span className="stat-value">128</span>
                <span className="stat-trend text-green">↑ 18.7% <span className="trend-vs">vs yesterday</span></span>
              </div>
            </div>

            <div className="stat-box">
              <div className="stat-icon-wrapper bg-green-10">
                <User className="text-green" size={22} />
              </div>
              <div className="stat-details">
                <span className="stat-label">Currently Inside</span>
                <span className="stat-value">12</span>
                <span className="stat-trend text-green flex-center gap-1"><span className="live-dot"></span> Live</span>
              </div>
            </div>

            <div className="stat-box">
              <div className="stat-icon-wrapper bg-orange-10">
                <ArrowRightToLine className="text-orange" size={22} />
              </div>
              <div className="stat-details">
                <span className="stat-label">Total Entries</span>
                <span className="stat-value">128</span>
                <span className="stat-trend text-green">↑ 18.7% <span className="trend-vs">vs yesterday</span></span>
              </div>
            </div>

            <div className="stat-box">
              <div className="stat-icon-wrapper bg-red-10">
                <ArrowLeftFromLine className="text-red" size={22} />
              </div>
              <div className="stat-details">
                <span className="stat-label">Total Exits</span>
                <span className="stat-value">116</span>
                <span className="stat-trend text-red">↓ 12.4% <span className="trend-vs">vs yesterday</span></span>
              </div>
            </div>
          </div>

          <div className="features-row">
            <div className="feature-item">
              <div className="feature-icon"><ScanFace size={20} /></div>
              <span className="feature-title">Live Detection</span>
              <span className="feature-desc">Real-time tracking</span>
            </div>
            <div className="feature-item">
              <div className="feature-icon"><BarChart3 size={20} /></div>
              <span className="feature-title">Smart Analytics</span>
              <span className="feature-desc">Actionable insights</span>
            </div>
            <div className="feature-item">
              <div className="feature-icon"><ShieldCheck size={20} /></div>
              <span className="feature-title">Secure & Reliable</span>
              <span className="feature-desc">Enterprise grade security</span>
            </div>
            <div className="feature-item">
              <div className="feature-icon"><Monitor size={20} /></div>
              <span className="feature-title">Intelligent Dashboard</span>
              <span className="feature-desc">Monitor. Analyze. Act.</span>
            </div>
          </div>
        </div>

        {/* Right Side */}
        <div className="login-right-panel">
          <div className="login-card">
            <div className="card-brand-center">
              <div className="card-logo-container">
                <Store className="card-logo-icon" size={32} />
              </div>
              <h2 className="card-brand-name">Bachhraj</h2>
              <span className="card-brand-sub">Smart Retail</span>
            </div>

            <div className="card-header-text">
              <h3>Welcome Back!</h3>
            </div>

            {error && (
              <div className="error-banner">
                <span className="error-dot">!</span>
                {error}
              </div>
            )}

            <form onSubmit={handleLogin} className="card-form">
              <div className="form-group">
                <label>Email Address</label>
                <div className="input-with-icon">
                  <Mail className="left-icon" size={18} />
                  <input 
                    type="email" 
                    placeholder="Enter your email address" 
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <div className="label-row">
                  <label>Password</label>
                  <a href="#" className="forgot-link">Forgot Password?</a>
                </div>
                <div className="input-with-icon">
                  <Lock className="left-icon" size={18} />
                  <input 
                    type={showPassword ? "text" : "password"} 
                    placeholder="Enter your password" 
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                  <button 
                    type="button" 
                    className="right-icon-btn" 
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              <div className="remember-row">
                <label className="checkbox-label">
                  <input type="checkbox" />
                  <span>Remember me</span>
                </label>
              </div>

              <button type="submit" className="primary-btn" disabled={loading}>
                <Lock size={16} />
                {loading ? 'Signing In...' : 'Sign In'}
              </button>
            </form>
          </div>
          
          <div className="copyright-text">
            © 2025 Bachhraj Smart Retail. All rights reserved.
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
