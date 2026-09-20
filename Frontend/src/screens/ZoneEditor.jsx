import React, { useRef, useState, useEffect, useCallback } from 'react';
import { createZone, updateZone, updateZonePolygon, deleteZone, fetchCameraZones } from '../Services/ZoneEditorservice';

const ZONE_COLORS = ['#3b82f6','#22c55e','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#ec4899','#84cc16'];
const ZONE_TYPES  = ['Entrance','Main Floor','Billing Counter','Product Shelf','Exit','Storage','Parking','Custom'];
const ZONE_TYPE_MAP = {
  'Entrance':'ENTRANCE','Main Floor':'SERVICE_ZONE','Billing Counter':'BILLING_COUNTER',
  'Product Shelf':'SERVICE_ZONE','Exit':'EXIT','Storage':'STAFF_AREA','Parking':'SERVICE_ZONE','Custom':'SERVICE_ZONE',
};

export default function ZoneEditor({ cam, jobId, storeId, onClose }) {
  const canvasRef    = useRef(null);
  const wsRef        = useRef(null);
  const frameRef     = useRef(null);

  const [zones, setZones]           = useState([]);
  const [drawing, setDrawing]       = useState(false);
  const [currentPts, setCurrentPts] = useState([]);
  const [zoneName, setZoneName]     = useState('');
  const [zoneType, setZoneType]     = useState('Entrance');
  const [saving, setSaving]         = useState(false);
  const [streamOk, setStreamOk]     = useState(false);
  const [canvasSize, setCanvasSize] = useState({ w: 854, h: 480 });
  const [editingZone, setEditingZone] = useState(null); // zone being edited
  const [editName, setEditName]     = useState('');
  const [editType, setEditType]     = useState('Entrance');
  const [repolygonZone, setRepolygonZone] = useState(null); // zone whose polygon is being redrawn

  // Load existing zones for this camera
  useEffect(() => {
    if (!cam?.id) return;
    fetchCameraZones(cam.id).then(setZones).catch(() => {});
  }, [cam?.id]);

  // WebSocket stream
  useEffect(() => {
    if (!jobId) return;
    const AI_BASE = import.meta.env.VITE_AI_BASE || 'http://localhost:8001';
    const wsUrl = `${AI_BASE.replace('http', 'ws')}/ws/stream/${jobId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.binaryType = 'arraybuffer';

    ws.onmessage = async (evt) => {
      if (typeof evt.data === 'string') return;
      try {
        const blob = new Blob([evt.data], { type: 'image/jpeg' });
        const bmp  = await createImageBitmap(blob);
        frameRef.current = bmp;
        setStreamOk(true);
        setCanvasSize({ w: bmp.width, h: bmp.height });
      } catch {}
    };

    return () => { ws.close(); wsRef.current = null; };
  }, [jobId]);

  // Draw loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let raf;

    const draw = () => {
      const ctx = canvas.getContext('2d');
      const { w, h } = canvasSize;
      canvas.width  = w;
      canvas.height = h;

      // Draw video frame
      if (frameRef.current) {
        ctx.drawImage(frameRef.current, 0, 0, w, h);
      } else {
        ctx.fillStyle = '#0f172a';
        ctx.fillRect(0, 0, w, h);
        ctx.fillStyle = '#475569';
        ctx.font = '16px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Waiting for stream…', w / 2, h / 2);
      }

      // Draw saved zones
      zones.forEach((z, zi) => {
        const pts = z.polygon?.points;
        if (!pts || pts.length < 2) return;
        const color = ZONE_COLORS[zi % ZONE_COLORS.length];
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        pts.slice(1).forEach(p => ctx.lineTo(p[0], p[1]));
        ctx.closePath();
        ctx.fillStyle   = color + '33';
        ctx.strokeStyle = color;
        ctx.lineWidth   = 2;
        ctx.fill();
        ctx.stroke();
        // Label
        const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
        const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
        ctx.fillStyle = color;
        ctx.font = 'bold 13px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(z.name, cx, cy);
      });

      // Draw current polygon being drawn
      if (currentPts.length > 0) {
        ctx.beginPath();
        ctx.moveTo(currentPts[0][0], currentPts[0][1]);
        currentPts.slice(1).forEach(p => ctx.lineTo(p[0], p[1]));
        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth   = 2;
        ctx.setLineDash([6, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
        // Dots
        currentPts.forEach(p => {
          ctx.beginPath();
          ctx.arc(p[0], p[1], 5, 0, Math.PI * 2);
          ctx.fillStyle = '#f59e0b';
          ctx.fill();
        });
      }

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [zones, currentPts, canvasSize]);

  const handleCanvasClick = useCallback((e) => {
    if (!drawing) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const scaleX = canvasSize.w / rect.width;
    const scaleY = canvasSize.h / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top)  * scaleY;
    setCurrentPts(p => [...p, [Math.round(x), Math.round(y)]]);
  }, [drawing, canvasSize]);

  const handleSaveZone = async () => {
    if (currentPts.length < 3) return alert('Minimum 3 points required');
    if (!zoneName.trim()) return alert('Zone name required');
    setSaving(true);
    try {
      if (repolygonZone) {
        // Update polygon only for existing zone
        const updated = await updateZonePolygon(repolygonZone.id, { points: currentPts });
        setZones(z => z.map(x => x.id === repolygonZone.id ? { ...x, polygon: updated?.polygon || { points: currentPts } } : x));
        setRepolygonZone(null);
      } else {
        const payload = {
          cameraId: cam.id, storeId,
          zoneCode: `${cam.id}_${Date.now()}`,
          name: zoneName.trim(),
          zoneType: ZONE_TYPE_MAP[zoneType] || 'SERVICE_ZONE',
          polygon: { points: currentPts },
          status: 'ACTIVE',
        };
        const saved = await createZone(payload);
        setZones(z => [...z, saved]);
      }
      setCurrentPts([]);
      setZoneName('');
      setDrawing(false);
    } catch (e) {
      alert('Save failed: ' + e.message);
    }
    setSaving(false);
  };

  const handleUpdateZoneMeta = async (zone) => {
    try {
      await updateZone(zone.id, { name: editName.trim(), zoneType: ZONE_TYPE_MAP[editType] || 'SERVICE_ZONE' });
      setZones(z => z.map(x => x.id === zone.id ? { ...x, name: editName.trim(), zone_type: ZONE_TYPE_MAP[editType] } : x));
      setEditingZone(null);
    } catch (e) { alert('Update failed: ' + e.message); }
  };

  const handleDeleteZone = async (zoneId) => {
    if (!confirm('Delete this zone?')) return;
    await deleteZone(zoneId).catch(() => {});
    setZones(z => z.filter(x => x.id !== zoneId));
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.85)',
      zIndex: 1000, display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', padding: 16,
    }}>
      <div style={{
        background: '#0f172a', borderRadius: 12, border: '1px solid #1e293b',
        width: '100%', maxWidth: 1100, maxHeight: '95vh', overflow: 'auto',
        display: 'flex', flexDirection: 'column', gap: 0,
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', borderBottom: '1px solid #1e293b',
        }}>
          <div>
            <span style={{ color: '#f1f5f9', fontWeight: 700, fontSize: 15 }}>
              Zone Editor — {cam?.name}
            </span>
            <span style={{ color: '#64748b', fontSize: 12, marginLeft: 8 }}>
              {streamOk ? '● Live' : '○ Connecting…'}
            </span>
          </div>
          <button onClick={onClose} style={{
            background: '#1e293b', border: 'none', color: '#94a3b8',
            borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontSize: 13,
          }}>✕ Close</button>
        </div>

        <div style={{ display: 'flex', gap: 0 }}>
          {/* Canvas */}
          <div style={{ flex: 1, position: 'relative', minHeight: 300 }}>
            <canvas
              ref={canvasRef}
              onClick={handleCanvasClick}
              style={{
                width: '100%', height: 'auto', display: 'block',
                cursor: drawing ? 'crosshair' : 'default',
              }}
            />
            {drawing && (
              <div style={{
                position: 'absolute', top: 8, left: 8,
                background: 'rgba(245,158,11,.9)', color: '#000',
                borderRadius: 6, padding: '4px 10px', fontSize: 11, fontWeight: 700,
              }}>
                Click to add points • {currentPts.length} pts
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div style={{
            width: 240, background: '#0a1628', borderLeft: '1px solid #1e293b',
            padding: 14, display: 'flex', flexDirection: 'column', gap: 12,
          }}>
            {/* Draw controls */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={{ color: '#94a3b8', fontSize: 11, fontWeight: 600, textTransform: 'uppercase' }}>
                New Zone
              </span>
              <input
                placeholder="Zone name"
                value={zoneName}
                onChange={e => setZoneName(e.target.value)}
                style={{
                  background: '#1e293b', border: '1px solid #334155', borderRadius: 6,
                  color: '#f1f5f9', padding: '6px 10px', fontSize: 12, outline: 'none',
                }}
              />
              <select
                value={zoneType}
                onChange={e => setZoneType(e.target.value)}
                style={{
                  background: '#1e293b', border: '1px solid #334155', borderRadius: 6,
                  color: '#f1f5f9', padding: '6px 10px', fontSize: 12, outline: 'none',
                }}
              >
                {ZONE_TYPES.map(t => <option key={t}>{t}</option>)}
              </select>

              {!drawing ? (
                <button
                  onClick={() => { setDrawing(true); setCurrentPts([]); setRepolygonZone(null); }}
                  style={{
                    background: '#0057ff', border: 'none', color: '#fff',
                    borderRadius: 6, padding: '7px 0', cursor: 'pointer', fontSize: 12, fontWeight: 600,
                  }}
                >
                  ✏ Draw Polygon
                </button>
              ) : (
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    onClick={handleSaveZone}
                    disabled={saving || currentPts.length < 3}
                    style={{
                      flex: 1, background: '#22c55e', border: 'none', color: '#fff',
                      borderRadius: 6, padding: '7px 0', cursor: 'pointer', fontSize: 12, fontWeight: 600,
                      opacity: currentPts.length < 3 ? 0.5 : 1,
                    }}
                  >
                    {saving ? '…' : repolygonZone ? '✓ Update Polygon' : '✓ Save'}
                  </button>
                  <button
                    onClick={() => { setDrawing(false); setCurrentPts([]); }}
                    style={{
                      flex: 1, background: '#ef4444', border: 'none', color: '#fff',
                      borderRadius: 6, padding: '7px 0', cursor: 'pointer', fontSize: 12,
                    }}
                  >
                    ✕ Cancel
                  </button>
                </div>
              )}
              {drawing && currentPts.length > 0 && (
                <button
                  onClick={() => setCurrentPts(p => p.slice(0, -1))}
                  style={{
                    background: '#1e293b', border: '1px solid #334155', color: '#94a3b8',
                    borderRadius: 6, padding: '5px 0', cursor: 'pointer', fontSize: 11,
                  }}
                >
                  ↩ Undo last point
                </button>
              )}
            </div>

            {/* Saved zones list */}
            <div style={{ borderTop: '1px solid #1e293b', paddingTop: 12 }}>
              <span style={{ color: '#94a3b8', fontSize: 11, fontWeight: 600, textTransform: 'uppercase' }}>
                Saved Zones ({zones.length})
              </span>
              <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {zones.length === 0 && (
                  <span style={{ color: '#475569', fontSize: 11 }}>No zones yet</span>
                )}
                {zones.map((z, i) => (
                  <div key={z.id} style={{
                    background: '#1e293b', borderRadius: 6, padding: '6px 10px',
                    display: 'flex', flexDirection: 'column', gap: 4,
                    borderLeft: `3px solid ${ZONE_COLORS[i % ZONE_COLORS.length]}`,
                  }}>
                    {editingZone?.id === z.id ? (
                      <>
                        <input value={editName} onChange={e => setEditName(e.target.value)}
                          style={{ background:'#0f172a', border:'1px solid #334155', borderRadius:4, color:'#f1f5f9', padding:'3px 7px', fontSize:11, outline:'none' }} />
                        <select value={editType} onChange={e => setEditType(e.target.value)}
                          style={{ background:'#0f172a', border:'1px solid #334155', borderRadius:4, color:'#f1f5f9', padding:'3px 6px', fontSize:11, outline:'none' }}>
                          {ZONE_TYPES.map(t => <option key={t}>{t}</option>)}
                        </select>
                        <div style={{ display:'flex', gap:4 }}>
                          <button onClick={() => handleUpdateZoneMeta(z)} style={{ flex:1, background:'#22c55e', border:'none', color:'#fff', borderRadius:4, padding:'3px 0', cursor:'pointer', fontSize:10 }}>Save</button>
                          <button onClick={() => setEditingZone(null)} style={{ flex:1, background:'#475569', border:'none', color:'#fff', borderRadius:4, padding:'3px 0', cursor:'pointer', fontSize:10 }}>Cancel</button>
                        </div>
                      </>
                    ) : (
                      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                        <div>
                          <div style={{ color:'#f1f5f9', fontSize:12, fontWeight:600 }}>{z.name}</div>
                          <div style={{ color:'#64748b', fontSize:10 }}>{z.zone_type}</div>
                        </div>
                        <div style={{ display:'flex', gap:2 }}>
                          <button onClick={() => { setEditingZone(z); setEditName(z.name); setEditType(Object.keys(ZONE_TYPE_MAP).find(k=>ZONE_TYPE_MAP[k]===z.zone_type)||'Entrance'); }}
                            style={{ background:'none', border:'none', color:'#94a3b8', cursor:'pointer', fontSize:12, padding:'0 3px' }} title="Edit">✏</button>
                          <button onClick={() => { setRepolygonZone(z); setZoneName(z.name); setDrawing(true); setCurrentPts([]); }}
                            style={{ background:'none', border:'none', color:'#f59e0b', cursor:'pointer', fontSize:12, padding:'0 3px' }} title="Redraw polygon">⬡</button>
                          <button onClick={() => handleDeleteZone(z.id)}
                            style={{ background:'none', border:'none', color:'#ef4444', cursor:'pointer', fontSize:14, padding:'0 3px' }}>🗑</button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
