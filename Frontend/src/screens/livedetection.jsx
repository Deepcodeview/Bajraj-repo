import { useState, useEffect, useCallback } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import { RefreshCw, Wifi, WifiOff, CheckCircle } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import {
  fetchStores, fetchZones, fetchAlerts, acknowledgeAlert,
  fetchAIHealth, fetchAIEvents, fetchAIAnalytics, fetchPersons,
  CAMERAS, startCameraJob, stopCameraJob, stopAllJobs,
  getJobStreamUrl, fetchJobResult,
} from '../Services/Livedetectionservice';
import '../Style/Livedetection.css';

const SEV_COLOR = { CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#f59e0b', LOW: '#3b82f6' };
const timeAgo = (d) => {
  const s = Math.floor((Date.now() - new Date(d)) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
};

// ── Camera Tile ───────────────────────────────────────────────────
// Overlays are position:absolute so MJPEG repaints don't cause reflow/flicker
function CamTile({ cam, jobId, metrics, starting, onStart, onStop, large }) {
  const isLive = !!jobId;
  const isStarting = !!starting;
  const inside = metrics?.currently_inside ?? 0;

  return (
    <div
      className={`ld-cam-tile ${large ? 'ld-cam-tile-large' : ''}`}
      style={{ border: `2px solid ${isLive ? '#22c55e' : '#1e293b'}` }}
    >
      {/* Stream fills the tile */}
      {isLive ? (
        <img
          src={getJobStreamUrl(jobId)}
          alt={cam.name}
          className="ld-cam-tile-img"
          onError={e => { e.target.style.opacity = '0.1'; }}
        />
      ) : (
        <div className="ld-cam-tile-dead">
          <WifiOff size={18} color="#6b7280" />
          <span>{cam.name} — {cam.label}</span>
        </div>
      )}

      {/* TOP overlay — absolutely positioned, no reflow on stream repaint */}
      <div className="ld-cam-tile-bar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className={`ld-dot ${isLive ? 'green' : 'red'}`} />
          <span className="ld-cam-tile-id">{cam.name}</span>
          <span style={{ fontSize: 10, color: '#cbd5e1' }}>{cam.label}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {isLive && (
            <span style={{
              fontSize: 10, fontWeight: 700, color: '#22c55e',
              background: 'rgba(34,197,94,.2)', border: '1px solid rgba(34,197,94,.4)',
              borderRadius: 20, padding: '2px 8px',
            }}>● LIVE</span>
          )}
          {isLive && (
            <span style={{
              fontSize: 10, background: 'rgba(0,0,0,.65)', borderRadius: 4,
              padding: '2px 6px', color: '#fff',
            }}>{inside} people</span>
          )}
        </div>
      </div>

      {/* BOTTOM overlay — absolutely positioned */}
      <div className="ld-cam-ctrl-bar">
        <span style={{ fontSize: 10, color: '#94a3b8' }}>
          {isStarting ? 'Connecting…' : isLive ? '1920×1080 • AI ON' : 'Offline'}
        </span>
        <button
          onClick={() => isLive ? onStop(cam) : onStart(cam)}
          disabled={isStarting}
          className={`ld-cam-start-btn ${isLive ? 'stop' : 'start'}`}
          style={{ opacity: isStarting ? 0.6 : 1, pointerEvents: 'auto' }}
        >
          {isStarting ? '⏳' : isLive ? '⏹ Stop' : '▶ Start'}
        </button>
      </div>
    </div>
  );
}

// ── Main screen ───────────────────────────────────────────────────
const LiveDetection = () => {
  const [stores, setStores]               = useState([]);
  const [selectedStore, setSelectedStore] = useState(null);
  const [zones, setZones]                 = useState([]);
  const [alerts, setAlerts]               = useState([]);
  const [aiOnline, setAiOnline]           = useState(false);
  const [analytics, setAnalytics]         = useState(null);
  const [persons, setPersons]             = useState([]);
  const [aiEvents, setAiEvents]           = useState([]);
  const [trendData, setTrendData]         = useState([]);
  const [selectedCam, setSelectedCam]     = useState(0);

  const [jobMap, setJobMap] = useState(() => {
    try { return JSON.parse(localStorage.getItem('ldJobMap') || '{}'); } catch { return {}; }
  });
  const [camMetrics, setCamMetrics] = useState({});
  const [starting, setStarting]     = useState({});
  const [startingAll, setStartingAll] = useState(false);

  useEffect(() => {
    localStorage.setItem('ldJobMap', JSON.stringify(jobMap));
  }, [jobMap]);

  useEffect(() => {
    const jids = Object.entries(jobMap);
    if (!jids.length) return;
    const t = setInterval(() => {
      jids.forEach(([camId, jobId]) => {
        fetchJobResult(jobId)
          .then(d => {
            if (!d) return; // null = 404, job gone — keep as-is, don't remove
            if (d?.analytics) setCamMetrics(p => ({ ...p, [camId]: d.analytics }));
            // only remove if explicitly failed
            if (d?.status === 'failed') {
              setJobMap(p => { const n = { ...p }; delete n[camId]; return n; });
              setCamMetrics(p => { const n = { ...p }; delete n[camId]; return n; });
            }
          })
          .catch(() => {}); // ignore network errors, keep camera live
      });
    }, 4000);
    return () => clearInterval(t);
  }, [jobMap]);

  const handleStart = useCallback(async (cam) => {
    setStarting(p => ({ ...p, [cam.id]: true }));
    try {
      const d = await startCameraJob(cam);
      if (d?.job_id) setJobMap(p => ({ ...p, [cam.id]: d.job_id }));
      else alert(d?.detail || 'Failed to start camera. Check AI server.');
    } catch (e) { alert(e.message); }
    setStarting(p => ({ ...p, [cam.id]: false }));
  }, []);

  const handleStop = useCallback(async (cam) => {
    const jobId = jobMap[cam.id];
    if (jobId) await stopCameraJob(jobId).catch(() => {});
    setJobMap(p => { const n = { ...p }; delete n[cam.id]; return n; });
    setCamMetrics(p => { const n = { ...p }; delete n[cam.id]; return n; });
  }, [jobMap]);

  const handleStartAll = useCallback(async () => {
    setStartingAll(true);
    for (const cam of CAMERAS) {
      if (!jobMap[cam.id]) {
        await handleStart(cam);
        await new Promise(r => setTimeout(r, 800));
      }
    }
    setStartingAll(false);
  }, [jobMap, handleStart]);

  const handleStopAll = useCallback(async () => {
    await stopAllJobs().catch(() => {});
    setJobMap({});
    setCamMetrics({});
  }, []);

  const loadBackend = useCallback(async () => {
    try {
      const list = await fetchStores();
      setStores(list);
      const first = list[0] || null;
      setSelectedStore(first);
      if (first) {
        const [z, a] = await Promise.all([fetchZones(first.id), fetchAlerts(first.id)]);
        setZones(z); setAlerts(a);
      }
    } catch {}
  }, []);

  const loadAI = useCallback(async () => {
    try {
      const health = await fetchAIHealth();
      setAiOnline(health?.status === 'ok');
      const [evts, anl, prs] = await Promise.all([
        fetchAIEvents(), fetchAIAnalytics(), fetchPersons(),
      ]);
      setAnalytics(anl);
      setPersons(prs?.cameras ? Object.values(prs.cameras).flatMap(c => c.persons || []) : []);
      setAiEvents(evts?.events || []);
      const now = Date.now();
      const buckets = Array.from({ length: 8 }, (_, i) => ({
        t: `${new Date(now - (7 - i) * 3600000).getHours()}:00`, v: 0,
      }));
      (evts?.events || []).forEach(ev => {
        const idx = Math.min(7, Math.floor((now - new Date(ev.timestamp).getTime()) / 3600000));
        buckets[7 - idx].v++;
      });
      setTrendData(buckets);
    } catch { setAiOnline(false); }
  }, []);

  const handleStoreChange = async (id) => {
    const s = stores.find(x => x.id === id);
    setSelectedStore(s);
    const [z, a] = await Promise.all([fetchZones(id), fetchAlerts(id)]);
    setZones(z); setAlerts(a);
  };

  useEffect(() => { loadBackend(); loadAI(); }, [loadBackend, loadAI]);
  useEffect(() => { const id = setInterval(loadAI, 15000); return () => clearInterval(id); }, [loadAI]);
  useEffect(() => {
    const id = setInterval(() => {
      if (selectedStore) fetchAlerts(selectedStore.id).then(setAlerts).catch(() => {});
    }, 30000);
    return () => clearInterval(id);
  }, [selectedStore]);

  const activeCam  = CAMERAS[selectedCam];
  const activeCams = Object.keys(jobMap).length;
  const zoneColors = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];
  const peakHour   = trendData.reduce((a, b) => b.v > a.v ? b : a, { t: '--', v: 0 });

  return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="main-content-wrapper">
        <Header title="Live Detection" subtitle="Real-time AI camera feeds" />
        <div className="ld-scroll">

          <div className="ld-store-bar">
            <span className="ld-store-label">Store:</span>
            <select className="ld-store-select" value={selectedStore?.id || ''}
              onChange={e => handleStoreChange(e.target.value)}>
              {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <span className={`ld-ai-status ${aiOnline ? 'online' : 'offline'}`}>
              {aiOnline ? <Wifi size={12} /> : <WifiOff size={12} />}
              AI {aiOnline ? 'Online' : 'Offline'}
            </span>
            <span className="ld-enrolled-badge">{activeCams}/{CAMERAS.length} live</span>
            {activeCams < CAMERAS.length ? (
              <button className="ld-expand-btn" disabled={startingAll} onClick={handleStartAll}
                style={{ background: '#0057ff', color: '#fff', border: 'none', opacity: startingAll ? 0.7 : 1 }}>
                {startingAll ? `⏳ Starting… (${activeCams}/${CAMERAS.length})` : '▶ Start All'}
              </button>
            ) : (
              <button className="ld-expand-btn" onClick={handleStopAll}
                style={{ background: '#dc2626', color: '#fff', border: 'none' }}>
                ⏹ Stop All
              </button>
            )}
            <button className="ld-expand-btn" style={{ marginLeft: 'auto' }}
              onClick={() => { loadBackend(); loadAI(); }}>
              <RefreshCw size={11} /> Refresh
            </button>
          </div>

          <div className="ld-stats-row">
            <div className="ld-stat-card">
              <div className="ld-stat-label">Active Faces</div>
              <div className="ld-stat-value">{analytics?.active_tracks ?? 0}</div>
              <span className="ld-live-badge"><span className={`ld-dot ${aiOnline ? 'green' : 'red'}`} />{aiOnline ? 'Live' : 'Offline'}</span>
            </div>
            <div className="ld-stat-card">
              <div className="ld-stat-label">Live Cameras</div>
              <div className="ld-stat-value">{activeCams}</div>
              <span className="ld-trend green">of {CAMERAS.length} total</span>
            </div>
            <div className="ld-stat-card">
              <div className="ld-stat-label">Open Alerts</div>
              <div className="ld-stat-value">{alerts.length}</div>
              <span className={`ld-trend ${alerts.length > 0 ? 'red' : 'green'}`}>
                {alerts.length > 0 ? '⚠ Needs attention' : '✓ All clear'}
              </span>
            </div>
            <div className="ld-stat-card">
              <div className="ld-stat-label">Peak Hour</div>
              <div className="ld-stat-value">{peakHour.t}</div>
              <span className="ld-sub-badge">{peakHour.v} detections</span>
            </div>
          </div>

          <div className="ld-main-grid">
            <div className="ld-left">

              <div className="ld-card p0">
                <div className="ld-card-header">
                  <div>
                    <span className="ld-card-title">Primary Camera</span>
                    <span className="ld-card-sub"> {selectedStore?.name || '—'} • InsightFace AI</span>
                  </div>
                  <div className="ld-header-right">
                    {CAMERAS.map((c, i) => (
                      <button key={c.id}
                        className={`ld-cam-tab ${selectedCam === i ? 'active' : ''}`}
                        onClick={() => setSelectedCam(i)}>
                        {c.name}
                      </button>
                    ))}
                  </div>
                </div>
                <CamTile
                  cam={activeCam}
                  jobId={jobMap[activeCam.id] || null}
                  metrics={camMetrics[activeCam.id] || null}
                  starting={starting[activeCam.id]}
                  onStart={handleStart}
                  onStop={handleStop}
                  large
                />
                <div className="ld-timeline">
                  <div className="ld-timeline-bar">
                    {trendData.filter(d => d.v > 0).map((d, i) => (
                      <span key={i} className="ld-tl-mark" style={{ left: `${(i / 8) * 100}%` }} />
                    ))}
                  </div>
                  <div className="ld-timeline-labels">
                    {trendData.map(d => <span key={d.t}>{d.t}</span>)}
                  </div>
                </div>
              </div>

              <div className="ld-card">
                <div className="ld-card-header">
                  <div>
                    <div className="ld-card-title">All Camera Feeds</div>
                    <div className="ld-card-sub">{CAMERAS.length} cameras • {activeCams} live</div>
                  </div>
                </div>
                <div className="ld-multicam-grid">
                  {CAMERAS.map(c => (
                    <CamTile key={c.id} cam={c}
                      jobId={jobMap[c.id] || null}
                      metrics={camMetrics[c.id] || null}
                      starting={starting[c.id]}
                      onStart={handleStart}
                      onStop={handleStop}
                    />
                  ))}
                </div>
              </div>

              {zones.length > 0 && (
                <div className="ld-card">
                  <div className="ld-card-title">Zone Overview</div>
                  <div className="ld-dwell-list">
                    {zones.slice(0, 5).map((z, i) => (
                      <div className="ld-dwell-row" key={z.id}>
                        <span className="ld-dwell-name">{z.name}</span>
                        <div className="ld-dwell-track">
                          <div className="ld-dwell-fill" style={{ width: `${[20,75,90,40,55][i]||30}%` }} />
                        </div>
                        <span className="ld-dwell-time">{z.zone_type}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="ld-right">

              <div className="ld-card">
                <div className="ld-card-header">
                  <span className="ld-card-title">Detection Trend</span>
                  <span className="ld-today-badge">Today</span>
                </div>
                <div style={{ height: 120, marginTop: 8 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={trendData} margin={{ top: 4, right: 0, left: -28, bottom: 0 }}>
                      <defs>
                        <linearGradient id="ldGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="t" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} />
                      <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} />
                      <Tooltip />
                      <Area type="monotone" dataKey="v" stroke="#6366f1" strokeWidth={2} fill="url(#ldGrad)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="ld-card">
                <div className="ld-card-title" style={{ marginBottom: 12 }}>Camera Grid Status</div>
                <div className="ld-camstatus-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
                  {CAMERAS.map(c => {
                    const live = !!jobMap[c.id];
                    const count = camMetrics[c.id]?.currently_inside ?? 0;
                    return (
                      <div key={c.id} style={{
                        background: live ? '#f0fdf4' : '#f8fafc',
                        border: `1px solid ${live ? '#bbf7d0' : '#e8ecf0'}`,
                        borderRadius: 8, padding: '8px 10px',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      }}>
                        <div>
                          <div style={{ fontSize: 10, fontWeight: 700, color: '#4a5568' }}>{c.name}</div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
                            <span className={`ld-dot ${live ? 'green' : 'red'}`} style={{ width: 5, height: 5 }} />
                            <span style={{ fontSize: 9, color: live ? '#16a34a' : '#94a3b8' }}>
                              {live ? 'live' : 'idle'}
                            </span>
                          </div>
                        </div>
                        <span style={{ fontWeight: 700, fontSize: 18, color: live ? '#0f1923' : '#94a3b8' }}>
                          {count}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {zones.length > 0 && (
                <div className="ld-card">
                  <div className="ld-card-header">
                    <div className="ld-card-title">People by Zone</div>
                    <span className="ld-today-badge">{zones.length} zones</span>
                  </div>
                  <div className="ld-zone-list">
                    {zones.slice(0, 6).map((z, i) => {
                      const pct = Math.max(10, ((i + 1) * 17) % 80 + 10);
                      return (
                        <div className="ld-zone-row" key={z.id}>
                          <span className="ld-zone-name">{z.name}</span>
                          <div className="ld-zone-track">
                            <div className="ld-zone-fill" style={{ width: `${pct}%`, background: zoneColors[i % 6] }} />
                          </div>
                          <span className="ld-zone-pct">{pct}%</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {analytics && (
                <div className="ld-card">
                  <div className="ld-card-title">AI Analytics</div>
                  <div className="ld-settings-list">
                    {[
                      ['Current Faces',    analytics.current_faces],
                      ['Active Tracks',    analytics.active_tracks],
                      ['Lost Tracks',      analytics.lost_tracks],
                      ['Total Unique',     analytics.total_unique_tracks],
                      ['Avg Frames/Track', analytics.avg_frames_tracked],
                    ].map(([label, val]) => (
                      <div className="ld-setting-row" key={label}>
                        <span className="ld-setting-name">{label}</span>
                        <span className="ld-threshold-val">{val}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {persons.length > 0 && (
                <div className="ld-card">
                  <div className="ld-card-header">
                    <div className="ld-card-title">Enrolled Persons</div>
                    <span className="ld-today-badge">{persons.length}</span>
                  </div>
                  <div className="ld-persons-grid">
                    {persons.map(p => (
                      <div className="ld-person-chip" key={p.name}>
                        <span className="ld-person-avatar">{p.name[0].toUpperCase()}</span>
                        <div>
                          <div className="ld-person-name">{p.name}</div>
                          <div className="ld-person-imgs">{p.images} images</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {aiEvents.length > 0 && (
                <div className="ld-card">
                  <div className="ld-card-header">
                    <div className="ld-card-title">Recent Events</div>
                    <span className="ld-today-badge">{aiEvents.length}</span>
                  </div>
                  <div className="ld-events-list">
                    {aiEvents.slice(0, 6).map((ev, i) => (
                      <div className="ld-event-row" key={i}>
                        <span className="ld-event-dot" style={{ background: ev.name === 'Unknown' ? '#f59e0b' : '#22c55e' }} />
                        <div className="ld-event-info">
                          <div className="ld-event-name">{ev.name}</div>
                          <div className="ld-event-time">{ev.timestamp ? timeAgo(ev.timestamp) : '--'}</div>
                        </div>
                        <span className="ld-event-conf">{ev.sim ? `${(ev.sim * 100).toFixed(0)}%` : ''}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="ld-card">
                <div className="ld-card-header">
                  <div className="ld-card-title">Live Alerts</div>
                  <button className="ld-expand-btn"
                    onClick={() => selectedStore && fetchAlerts(selectedStore.id).then(setAlerts)}>
                    <RefreshCw size={11} /> Refresh
                  </button>
                </div>
                <div className="ld-alerts-list">
                  {alerts.length === 0 ? (
                    <div className="ld-empty"><CheckCircle size={14} color="#22c55e" /> No open alerts</div>
                  ) : (
                    alerts.slice(0, 5).map(a => (
                      <div className="ld-alert-row" key={a.id}>
                        <span className="ld-alert-dot" style={{ background: SEV_COLOR[a.severity] || '#6b7280' }} />
                        <div className="ld-alert-info">
                          <div className="ld-alert-text">{a.title}</div>
                          <div className="ld-alert-sub">{a.severity} • {timeAgo(a.created_at)}</div>
                        </div>
                        <button className="ld-view-clip"
                          onClick={() => acknowledgeAlert(a.id).then(() => setAlerts(p => p.filter(x => x.id !== a.id)))}>
                          Ack
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>

            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LiveDetection;
