import { useState, useEffect } from 'react';
import { Plus, Pencil, Trash2, X, RefreshCw, Wifi, WifiOff, Camera } from 'lucide-react';
import Sidebar from './Sidebar';
import Header from './Header';
import { getCameras, createCamera, updateCamera, deleteCamera } from '../Services/Cameraservice';
import { getStores } from '../Services/StoreInfoservice';
import { useToast } from '../components/Toast';
import '../Style/dashboard.css';

const EMPTY_FORM = { cameraCode: '', name: '', storeId: '', streamReference: '', resolution: '', fps: '', status: 'ACTIVE' };

export default function CameraManagement() {
  const toast = useToast();
  const [cameras, setCameras]   = useState([]);
  const [stores, setStores]     = useState([]);
  const [loading, setLoading]   = useState(true);
  const [modal, setModal]       = useState(false);
  const [editing, setEditing]   = useState(null);
  const [form, setForm]         = useState(EMPTY_FORM);
  const [saving, setSaving]     = useState(false);
  const [filterStore, setFilterStore] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [camRes, storeRes] = await Promise.all([
        getCameras(filterStore ? { storeId: filterStore } : {}),
        getStores(),
      ]);
      setCameras(camRes.data || []);
      setStores(storeRes.data || []);
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filterStore]);

  const openCreate = () => {
    setEditing(null);
    setForm({ ...EMPTY_FORM, storeId: stores[0]?.id || '' });
    setModal(true);
  };

  const openEdit = (cam) => {
    setEditing(cam);
    setForm({
      cameraCode: cam.camera_code || '',
      name: cam.name || '',
      storeId: cam.store_id || '',
      streamReference: cam.stream_reference || '',
      resolution: cam.resolution || '',
      fps: cam.fps ? String(cam.fps) : '',
      status: cam.status || 'ACTIVE',
    });
    setModal(true);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editing) {
        await updateCamera(editing.id, form);
        toast('Camera updated successfully');
      } else {
        await createCamera(form);
        toast('Camera added successfully');
      }
      setModal(false);
      load();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this camera?')) return;
    try {
      await deleteCamera(id);
      toast('Camera deleted');
      load();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  const storeName = (id) => stores.find(s => s.id === id)?.name || '--';

  const online  = cameras.filter(c => c.health_status === 'ONLINE').length;
  const offline = cameras.filter(c => c.health_status !== 'ONLINE').length;

  const statCards = [
    { label: 'Total Cameras', value: cameras.length, bg: '#eff6ff', color: '#2563eb' },
    { label: 'Online',        value: online,          bg: '#f0fdf4', color: '#16a34a' },
    { label: 'Offline',       value: offline,         bg: '#fef2f2', color: '#dc2626' },
    { label: 'Active',        value: cameras.filter(c => c.status === 'ACTIVE').length, bg: '#fefce8', color: '#ca8a04' },
  ];

  return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="main-content-wrapper">
        <Header title="Camera Management" subtitle="Monitor and manage your camera network" />
        <div className="db-scroll">

          {/* Summary Cards */}
          <div className="db-stats-row">
            {statCards.map(c => (
              <div key={c.label} className="db-stat-card" style={{ background: c.bg, border: `1px solid ${c.color}22` }}>
                <div className="db-stat-label">{c.label}</div>
                <div className="db-stat-value" style={{ color: c.color, fontSize: 28, marginTop: 6 }}>{loading ? '...' : c.value}</div>
              </div>
            ))}
          </div>

          {/* Controls */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
            <select value={filterStore} onChange={e => setFilterStore(e.target.value)}
              style={{ padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, color: '#374151' }}>
              <option value="">All Stores</option>
              {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={load} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', fontSize: 13, cursor: 'pointer' }}>
                <RefreshCw size={14} /> Refresh
              </button>
              <button onClick={openCreate} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', border: 'none', borderRadius: 8, background: '#2563eb', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                <Plus size={15} /> Add Camera
              </button>
            </div>
          </div>

          {/* Camera Table */}
          <div className="db-card" style={{ padding: 0, overflow: 'hidden' }}>
            {loading ? (
              <div style={{ padding: 48, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e5e7eb', background: '#f9fafb' }}>
                    {['Camera', 'Code', 'Store', 'Resolution', 'FPS', 'Health', 'Status', 'Actions'].map(h => (
                      <th key={h} style={{ padding: '12px 20px', textAlign: 'left', fontSize: 13, fontWeight: 600, color: '#6b7280' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {cameras.length === 0 ? (
                    <tr><td colSpan={8} style={{ padding: 48, textAlign: 'center', color: '#6b7280' }}>No cameras found. Add your first camera.</td></tr>
                  ) : cameras.map(cam => (
                    <tr key={cam.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '13px 20px', fontSize: 14, fontWeight: 500, color: '#111827', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Camera size={15} color="#6366f1" /> {cam.name}
                      </td>
                      <td style={{ padding: '13px 20px', fontSize: 13, color: '#374151', fontFamily: 'monospace' }}>{cam.camera_code}</td>
                      <td style={{ padding: '13px 20px', fontSize: 13, color: '#374151' }}>{storeName(cam.store_id)}</td>
                      <td style={{ padding: '13px 20px', fontSize: 13, color: '#374151' }}>{cam.resolution || '--'}</td>
                      <td style={{ padding: '13px 20px', fontSize: 13, color: '#374151' }}>{cam.fps ? `${cam.fps} fps` : '--'}</td>
                      <td style={{ padding: '13px 20px' }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 600,
                          color: cam.health_status === 'ONLINE' ? '#16a34a' : '#dc2626' }}>
                          {cam.health_status === 'ONLINE' ? <Wifi size={13} /> : <WifiOff size={13} />}
                          {cam.health_status || 'OFFLINE'}
                        </span>
                      </td>
                      <td style={{ padding: '13px 20px' }}>
                        <span style={{ padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600,
                          background: cam.status === 'ACTIVE' ? '#dcfce7' : '#fee2e2',
                          color: cam.status === 'ACTIVE' ? '#16a34a' : '#dc2626' }}>
                          {cam.status}
                        </span>
                      </td>
                      <td style={{ padding: '13px 20px' }}>
                        <div style={{ display: 'flex', gap: 8 }}>
                          <button onClick={() => openEdit(cam)} style={{ padding: '5px 10px', border: '1px solid #d1d5db', borderRadius: 6, background: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, color: '#374151' }}>
                            <Pencil size={13} /> Edit
                          </button>
                          <button onClick={() => handleDelete(cam.id)} style={{ padding: '5px 10px', border: '1px solid #fca5a5', borderRadius: 6, background: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, color: '#ef4444' }}>
                            <Trash2 size={13} /> Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

        </div>
      </div>

      {modal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: '#fff', borderRadius: 12, padding: 28, width: 480, maxHeight: '90vh', overflowY: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>{editing ? 'Edit Camera' : 'Add Camera'}</h3>
              <button onClick={() => setModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280' }}><X size={20} /></button>
            </div>
            <form onSubmit={handleSave}>
              {[
                { label: 'Camera Code *', key: 'cameraCode', required: true, disabled: !!editing },
                { label: 'Name *',        key: 'name',       required: true },
                { label: 'Stream URL',    key: 'streamReference' },
                { label: 'Resolution',    key: 'resolution', placeholder: 'e.g. 1920x1080' },
                { label: 'FPS',           key: 'fps',        type: 'number', placeholder: 'e.g. 30' },
              ].map(f => (
                <div key={f.key} style={{ marginBottom: 14 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 5 }}>{f.label}</label>
                  <input
                    type={f.type || 'text'}
                    required={f.required}
                    disabled={f.disabled}
                    placeholder={f.placeholder || ''}
                    value={form[f.key]}
                    onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                    style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 7, fontSize: 14, boxSizing: 'border-box', background: f.disabled ? '#f9fafb' : '#fff' }}
                  />
                </div>
              ))}
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 5 }}>Store *</label>
                <select required value={form.storeId} onChange={e => setForm(p => ({ ...p, storeId: e.target.value }))}
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 7, fontSize: 14 }}>
                  <option value="">Select store</option>
                  {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 5 }}>Status</label>
                <select value={form.status} onChange={e => setForm(p => ({ ...p, status: e.target.value }))}
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 7, fontSize: 14 }}>
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="INACTIVE">INACTIVE</option>
                </select>
              </div>
              <div style={{ display: 'flex', gap: 10, marginTop: 22 }}>
                <button type="button" onClick={() => setModal(false)} style={{ flex: 1, padding: 10, border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', fontSize: 14, cursor: 'pointer' }}>Cancel</button>
                <button type="submit" disabled={saving} style={{ flex: 1, padding: 10, border: 'none', borderRadius: 8, background: saving ? '#93c5fd' : '#2563eb', color: '#fff', fontSize: 14, fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer' }}>
                  {saving ? 'Saving...' : editing ? 'Update' : 'Add Camera'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
