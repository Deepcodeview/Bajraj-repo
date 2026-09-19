import React, { useState, useEffect, useCallback } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import { RefreshCw, Wifi, WifiOff, CheckCircle } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import {
  fetchStores, fetchZones, fetchAlerts, acknowledgeAlert,
  fetchAIHealth, fetchAIEvents, fetchAIAnalytics, fetchPersons,
  CAMERAS, startCameraJob, stopCameraJob, stopAllJobs,
  getJobStreamUrl, getJobWsUrl, fetchJobResult, getRtspUrl,
} from '../Services/Livedetectionservice';
import { fetchCameraZones, createZone, deleteZone } from '../Services/ZoneEditorservice';
import '../Style/Livedetection.css';

const ZONE_COLORS = ['#3b82f6','#22c55e','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#ec4899','#84cc16'];
const ZONE_TYPES  = ['Entrance','Main Floor','Billing Counter','Product Shelf','Exit','Storage','Parking','Custom'];
const ZONE_TYPE_MAP = {
  'Entrance': 'ENTRANCE',
  'Main Floor': 'SERVICE_ZONE',
  'Billing Counter': 'BILLING_COUNTER',
  'Product Shelf': 'SERVICE_ZONE',
  'Exit': 'EXIT',
  'Storage': 'STAFF_AREA',
  'Parking': 'SERVICE_ZONE',
  'Custom': 'SERVICE_ZONE',
};

const SEV_COLOR = { CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#f59e0b', LOW: '#3b82f6' };
const timeAgo = (d) => {
  const s = Math.floor((Date.now() - new Date(d)) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
};

function CamTile({ cam, jobId, metrics, starting, onStart, onStop, large, storeId }) {
  const isLive    = !!jobId;
  const isStarting = !!starting;
  const inside    = metrics?.currently_inside ?? 0;

  const canvasRef  = React.useRef(null);
  const wsRef      = React.useRef(null);
  const frameRef   = React.useRef(null);
  const rafRef     = React.useRef(null);
  const canvasSize = React.useRef({ w: 854, h: 480 });
  const zonesRef   = React.useRef([]);
  const ptsRef     = React.useRef([]);
  const dirtyRef   = React.useRef(true);

  const [wsStatus,   setWsStatus]   = React.useState('idle');
  const [zoneMode,   setZoneMode]   = React.useState(false);
  const [drawing,    setDrawing]    = React.useState(false);
  const [currentPts, setCurrentPts] = React.useState([]);
  const [zones,      setZones]      = React.useState([]);
  const [zoneName,   setZoneName]   = React.useState('');
  const [zoneType,   setZoneType]   = React.useState('Entrance');
  const [saving,     setSaving]     = React.useState(false);

  // Sync refs so draw loop always has latest data without re-mounting
  React.useEffect(() => { zonesRef.current = zones; dirtyRef.current = true; }, [zones]);
  React.useEffect(() => { ptsRef.current = currentPts; dirtyRef.current = true; }, [currentPts]);

  // Load zones when zone mode opens
  React.useEffect(() => {
    if (!zoneMode || !cam?.id) return;
    fetchCameraZones(cam.id).then(setZones).catch(() => {});
  }, [zoneMode, cam?.id]);

  // WebSocket stream
  React.useEffect(() => {
    if (!isLive) { setWsStatus('idle'); return; }
    let destroyed = false;
    setWsStatus('connecting');
    const timer = setTimeout(() => {
      if (destroyed) return;
      const ws = new WebSocket(getJobWsUrl(jobId));
      wsRef.current = ws;
      ws.binaryType = 'arraybuffer';
      ws.onmessage = async (evt) => {
        if (destroyed || typeof evt.data === 'string') return;
        try {
          const bmp = await createImageBitmap(new Blob([evt.data], { type: 'image/jpeg' }));
          frameRef.current = bmp;
          canvasSize.current = { w: bmp.width, h: bmp.height };
          dirtyRef.current = true;
          setWsStatus('live');
        } catch {}
      };
      ws.onerror = () => { if (!destroyed) setWsStatus('error'); };
      ws.onclose = () => { if (!destroyed) setWsStatus(s => s === 'live' ? 'idle' : s); };
    }, 100);
    return () => {
      destroyed = true;
      clearTimeout(timer);
      if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    };
  }, [isLive, jobId]);

  // Draw loop — mounts once, reads latest data via refs
  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let lastFrame = null;
    const draw = () => {
      const hasNewFrame = frameRef.current !== lastFrame;
      const isDirty = dirtyRef.current;
      if (!hasNewFrame && !isDirty) {
        rafRef.current = requestAnimationFrame(draw);
        return;
      }
      lastFrame = frameRef.current;
      dirtyRef.current = false;

      const { w, h } = canvasSize.current;
      if (canvas.width !== w) canvas.width = w;
      if (canvas.height !== h) canvas.height = h;
      const ctx = canvas.getContext('2d');
      if (frameRef.current) {
        ctx.drawImage(frameRef.current, 0, 0, w, h);
      } else {
        ctx.fillStyle = '#0f172a';
        ctx.fillRect(0, 0, w, h);
      }
      zonesRef.current.forEach((z, zi) => {
        const pts = z.polygon?.points;
        if (!pts || pts.length < 2) return;
        const color = ZONE_COLORS[zi % ZONE_COLORS.length];
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        pts.slice(1).forEach(p => ctx.lineTo(p[0], p[1]));
        ctx.closePath();
        ctx.fillStyle = color + '44';
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.fill(); ctx.stroke();
        const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
        const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(z.name, cx, cy);
      });
      const pts = ptsRef.current;
      if (pts.length > 0) {
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        pts.slice(1).forEach(p => ctx.lineTo(p[0], p[1]));
        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
        pts.forEach(p => {
          ctx.beginPath();
          ctx.arc(p[0], p[1], 5, 0, Math.PI * 2);
          ctx.fillStyle = '#f59e0b';
          ctx.fill();
        });
      }
      rafRef.current = requestAnimationFrame(draw);
    };
    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  const handleCanvasClick = useCallback((e) => {
    if (!drawing) return;
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const { w, h } = canvasSize.current;
    const x = Math.round((e.clientX - rect.left) * (w / rect.width));
    const y = Math.round((e.clientY - rect.top)  * (h / rect.height));
    setCurrentPts(p => [...p, [x, y]]);
  }, [drawing]);

  const handleSave = async () => {
    if (currentPts.length < 3) return alert('Minimum 3 points required');
    if (!zoneName.trim()) return alert('Zone name required');
    setSaving(true);
    try {
      const saved = await createZone({
        cameraId: cam.id, storeId,
        zoneCode: `${cam.id}_${Date.now()}`,
        name: zoneName.trim(), zoneType: ZONE_TYPE_MAP[zoneType] || 'SERVICE_ZONE',
        polygon: { points: currentPts }, status: 'ACTIVE',
      });
      setZones(z => [...z, saved]);
      setCurrentPts([]); setZoneName(''); setDrawing(false);
    } catch (e) { alert('Save failed: ' + e.message); }
    setSaving(false);
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete zone?')) return;
    await deleteZone(id).catch(() => {});
    setZones(z => z.filter(x => x.id !== id));
  };

  return (
    <div
      className={`ld-cam-tile ${large ? 'ld-cam-tile-large' : ''}`}
      style={{ border: `2px solid ${zoneMode ? '#f59e0b' : isLive ? '#22c55e' : '#1e293b'}` }}
    >
      {isLive ? (
        <div style={{ position: 'relative', width: '100%', background: '#000', minHeight: 200 }}>
          {wsStatus !== 'live' && !zoneMode && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', gap: 8, zIndex: 2,
            }}>
              <div style={{
                width: 28, height: 28, border: '3px solid #22c55e',
                borderTopColor: 'transparent', borderRadius: '50%',
                animation: wsStatus === 'error' ? 'none' : 'spin 1s linear infinite',
              }} />
              <span style={{ fontSize: 10, color: wsStatus === 'error' ? '#ef4444' : '#22c55e' }}>
                {wsStatus === 'error' ? 'Stream Error' : 'Connecting…'}
              </span>
            </div>
          )}
          <canvas
            ref={canvasRef}
            onClick={handleCanvasClick}
            className="ld-cam-tile-img"
            style={{
              opacity: wsStatus === 'live' || zoneMode ? 1 : 0,
              transition: 'opacity 0.3s',
              cursor: drawing ? 'crosshair' : 'default',
              display: 'block', width: '100%', height: 'auto',
            }}
          />
          {drawing && (
            <div style={{
              position: 'absolute', top: 6, left: 6,
              background: 'rgba(245,158,11,.9)', color: '#000',
              borderRadius: 5, padding: '3px 8px', fontSize: 10, fontWeight: 700, zIndex: 3,
            }}>
              ✏ Click to add points • {currentPts.length} pts
            </div>
          )}

          {/* Zone mode panel */}
          {zoneMode && (
            <div style={{
              position: 'absolute', bottom: 0, left: 0, right: 0,
              background: 'rgba(10,22,40,.95)', borderTop: '1px solid #1e293b',
              padding: '8px 10px', zIndex: 4, display: 'flex', flexDirection: 'column', gap: 6,
            }}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <input
                  placeholder="Zone name"
                  value={zoneName}
                  onChange={e => setZoneName(e.target.value)}
                  style={{
                    flex: 1, minWidth: 80, background: '#1e293b', border: '1px solid #334155',
                    borderRadius: 5, color: '#f1f5f9', padding: '4px 8px', fontSize: 11, outline: 'none',
                  }}
                />
                <select
                  value={zoneType}
                  onChange={e => setZoneType(e.target.value)}
                  style={{
                    background: '#1e293b', border: '1px solid #334155', borderRadius: 5,
                    color: '#f1f5f9', padding: '4px 6px', fontSize: 11, outline: 'none',
                  }}
                >
                  {ZONE_TYPES.map(t => <option key={t}>{t}</option>)}
                </select>
                {!drawing ? (
                  <button onClick={() => { setDrawing(true); setCurrentPts([]); }} style={{
                    background: '#0057ff', border: 'none', color: '#fff',
                    borderRadius: 5, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600,
                  }}>✏ Draw</button>
                ) : (
                  <>
                    <button onClick={handleSave} disabled={saving || currentPts.length < 3} style={{
                      background: '#22c55e', border: 'none', color: '#fff',
                      borderRadius: 5, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600,
                      opacity: currentPts.length < 3 ? 0.5 : 1,
                    }}>{saving ? '…' : '✓ Save'}</button>
                    <button onClick={() => setCurrentPts(p => p.slice(0, -1))} style={{
                      background: '#1e293b', border: '1px solid #334155', color: '#94a3b8',
                      borderRadius: 5, padding: '4px 8px', cursor: 'pointer', fontSize: 11,
                    }}>↩</button>
                    <button onClick={() => { setDrawing(false); setCurrentPts([]); }} style={{
                      background: '#ef4444', border: 'none', color: '#fff',
                      borderRadius: 5, padding: '4px 8px', cursor: 'pointer', fontSize: 11,
                    }}>✕</button>
                  </>
                )}
                <button onClick={() => { setZoneMode(false); setDrawing(false); setCurrentPts([]); }} style={{
                  background: '#1e293b', border: '1px solid #475569', color: '#94a3b8',
                  borderRadius: 5, padding: '4px 8px', cursor: 'pointer', fontSize: 11, marginLeft: 'auto',
                }}>Close</button>
              </div>
              {zones.length > 0 && (
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  {zones.map((z, i) => (
                    <span key={z.id} style={{
                      background: ZONE_COLORS[i % ZONE_COLORS.length] + '33',
                      border: `1px solid ${ZONE_COLORS[i % ZONE_COLORS.length]}`,
                      borderRadius: 4, padding: '2px 7px', fontSize: 10, color: '#f1f5f9',
                      display: 'flex', alignItems: 'center', gap: 4,
                    }}>
                      {z.name}
                      <span onClick={() => handleDelete(z.id)}
                        style={{ cursor: 'pointer', color: '#ef4444', fontWeight: 700 }}>×</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="ld-cam-tile-dead">
          <WifiOff size={18} color="#6b7280" />
          <span>{cam.name} — {cam.label}</span>
        </div>
      )}

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

      <div className="ld-cam-ctrl-bar">
        <span style={{ fontSize: 10, color: '#94a3b8' }}>
          {isStarting ? 'Connecting…' : isLive ? '1920×1080 • AI ON' : 'Offline'}
        </span>
        <div style={{ display: 'flex', gap: 4 }}>
          {isLive && (
            <button
              onClick={() => setZoneMode(m => !m)}
              style={{
                background: zoneMode ? '#f59e0b' : '#1e293b',
                border: `1px solid ${zoneMode ? '#f59e0b' : '#334155'}`,
                color: zoneMode ? '#000' : '#94a3b8',
                borderRadius: 4, padding: '2px 7px', cursor: 'pointer', fontSize: 10, fontWeight: 600,
              }}
            >⬡ Zones</button>
          )}
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
    </div>
  );
}

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
  const [quality, setQuality]             = useState('high');

  const [jobMap, setJobMap] = useState(() => {
    try { return JSON.parse(localStorage.getItem('ldJobMap') || '{}'); } catch { return {}; }
  });
  const [camMetrics, setCamMetrics] = useState({});
  const [starting, setStarting]     = useState({});
  const [startingAll, setStartingAll] = useState(false);

  useEffect(() => {
    localStorage.setItem('ldJobMap', JSON.stringify(jobMap));
  }, [jobMap]);

  const jobMapRef = React.useRef(jobMap);
  useEffect(() => { jobMapRef.current = jobMap; }, [jobMap]);

  // Poll job results — runs once, always reads latest jobMap via ref
  useEffect(() => {
    const t = setInterval(() => {
      const jids = Object.entries(jobMapRef.current);
      if (!jids.length) return;
      jids.forEach(([camId, jobId]) => {
        fetchJobResult(jobId)
          .then(d => {
            if (!d) return; // network error — keep alive
            if (d.stale) {
              // job gone from backend (404) — clean up
              setJobMap(p => { const n = { ...p }; delete n[camId]; return n; });
              setCamMetrics(p => { const n = { ...p }; delete n[camId]; return n; });
              return;
            }
            if (d.analytics) setCamMetrics(p => ({ ...p, [camId]: d.analytics }));
          })
          .catch(() => {}); // never remove on network error
      });
    }, 4000);
    return () => clearInterval(t);
  }, []);

  const handleStart = useCallback(async (cam) => {
    setStarting(p => ({ ...p, [cam.id]: true }));
    try {
      const d = await startCameraJob(cam, quality);
      if (d?.job_id) {
        setJobMap(p => ({ ...p, [cam.id]: d.job_id }));
      } else {
        alert(d?.detail || d?.message || 'Failed to start camera. Check AI server.');
      }
    } catch (e) { alert(e.message); }
    setStarting(p => ({ ...p, [cam.id]: false }));
  }, [quality]);

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
      setPersons(prs.persons || []);
      const events = evts.events || [];
      setAiEvents(events);
      const now = Date.now();
      const buckets = Array.from({ length: 8 }, (_, i) => ({
        t: `${new Date(now - (7 - i) * 3600000).getHours()}:00`, v: 0,
      }));
      events.forEach(ev => {
        const idx = Math.min(7, Math.floor((now - new Date(ev.timestamp).getTime()) / 3600000));
        if (idx >= 0) buckets[7 - idx].v++;
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

  const activeCam  = CAMERAS[selectedCam] || CAMERAS[0];
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

            {/* Quality Toggle */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: '#1e293b', borderRadius: 6, padding: '2px 4px' }}>
              <button
                onClick={() => setQuality('high')}
                style={{ fontSize: 10, padding: '3px 8px', borderRadius: 4, border: 'none', cursor: 'pointer',
                  background: quality === 'high' ? '#0057ff' : 'transparent',
                  color: quality === 'high' ? '#fff' : '#94a3b8', fontWeight: 600 }}>
                HD
              </button>
              <button
                onClick={() => setQuality('low')}
                style={{ fontSize: 10, padding: '3px 8px', borderRadius: 4, border: 'none', cursor: 'pointer',
                  background: quality === 'low' ? '#f59e0b' : 'transparent',
                  color: quality === 'low' ? '#fff' : '#94a3b8', fontWeight: 600 }}>
                SD
              </button>
            </div>

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
                  storeId={selectedStore?.id}
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
                      storeId={selectedStore?.id}
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
                    {persons.filter(p => p && p.name).map(p => (
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
