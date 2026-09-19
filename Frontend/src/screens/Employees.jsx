import { useState, useEffect } from 'react';
import { Plus, Pencil, Trash2, X, ChevronLeft, ChevronRight } from 'lucide-react';
import Sidebar from './Sidebar';
import Header from './Header';
import { getEmployees, createEmployee, updateEmployee, deleteEmployee } from '../Services/Employeeservice';
import { getStores } from '../Services/StoreInfoservice';
import '../Style/dashboard.css';

const EMPTY_FORM = { firstName: '', lastName: '', employeeCode: '', email: '', phone: '', storeId: '', status: 'ACTIVE' };

const Employees = () => {
  const [employees, setEmployees] = useState([]);
  const [stores, setStores]       = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState('');
  const [modal, setModal]         = useState(false);
  const [editing, setEditing]     = useState(null);
  const [form, setForm]           = useState(EMPTY_FORM);
  const [saving, setSaving]       = useState(false);
  const [saveError, setSaveError] = useState('');
  const [page, setPage]           = useState(1);
  const PER_PAGE = 10;

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [empRes, storeRes] = await Promise.all([getEmployees(), getStores()]);
      setEmployees(empRes.data || []);
      setStores(storeRes.data || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const openCreate = () => {
    setEditing(null);
    setForm({ ...EMPTY_FORM, storeId: stores[0]?.id || '' });
    setSaveError('');
    setModal(true);
  };

  const openEdit = (emp) => {
    setEditing(emp);
    setForm({
      firstName: emp.first_name || '',
      lastName: emp.last_name || '',
      employeeCode: emp.employee_code || '',
      email: emp.email || '',
      phone: emp.phone || '',
      storeId: emp.store_id || '',
      status: emp.status || 'ACTIVE',
    });
    setSaveError('');
    setModal(true);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveError('');
    try {
      if (editing) await updateEmployee(editing.id, form);
      else await createEmployee(form);
      setModal(false);
      load();
    } catch (e) {
      setSaveError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this employee?')) return;
    try {
      await deleteEmployee(id);
      load();
    } catch (e) {
      alert(e.message);
    }
  };

  const paged      = employees.slice((page - 1) * PER_PAGE, page * PER_PAGE);
  const totalPages = Math.ceil(employees.length / PER_PAGE);

  const storeName = (id) => stores.find(s => s.id === id)?.name || id || '--';

  return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="main-content-wrapper">
        <Header title="Employees" subtitle="Manage your store employees" />
        <div className="db-scroll">
          <div className="db-card" style={{ padding: 0, overflow: 'hidden' }}>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #e5e7eb' }}>
              <span style={{ fontWeight: 700, fontSize: 15, color: '#111827' }}>
                All Employees {!loading && `(${employees.length})`}
              </span>
              <button onClick={openCreate} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
                <Plus size={16} /> Add Employee
              </button>
            </div>

            {loading ? (
              <div style={{ padding: 48, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
            ) : error ? (
              <div style={{ padding: 48, textAlign: 'center', color: '#ef4444' }}>{error}</div>
            ) : (
              <>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #e5e7eb', background: '#f9fafb' }}>
                      {['Name', 'Code', 'Email', 'Phone', 'Store', 'Status', 'Actions'].map(h => (
                        <th key={h} style={{ padding: '12px 20px', textAlign: 'left', fontSize: 13, fontWeight: 600, color: '#6b7280' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {paged.length === 0 ? (
                      <tr>
                        <td colSpan={7} style={{ padding: 48, textAlign: 'center', color: '#6b7280' }}>No employees found</td>
                      </tr>
                    ) : paged.map(emp => (
                      <tr key={emp.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                        <td style={{ padding: '13px 20px', fontSize: 14, fontWeight: 500, color: '#111827' }}>
                          {emp.first_name} {emp.last_name || ''}
                        </td>
                        <td style={{ padding: '13px 20px', fontSize: 14, color: '#374151' }}>{emp.employee_code || '--'}</td>
                        <td style={{ padding: '13px 20px', fontSize: 14, color: '#374151' }}>{emp.email || '--'}</td>
                        <td style={{ padding: '13px 20px', fontSize: 14, color: '#374151' }}>{emp.phone || '--'}</td>
                        <td style={{ padding: '13px 20px', fontSize: 14, color: '#374151' }}>{storeName(emp.store_id)}</td>
                        <td style={{ padding: '13px 20px' }}>
                          <span style={{ padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, background: emp.status === 'ACTIVE' ? '#dcfce7' : '#fee2e2', color: emp.status === 'ACTIVE' ? '#16a34a' : '#dc2626' }}>
                            {emp.status}
                          </span>
                        </td>
                        <td style={{ padding: '13px 20px' }}>
                          <div style={{ display: 'flex', gap: 8 }}>
                            <button onClick={() => openEdit(emp)} style={{ padding: '5px 10px', border: '1px solid #d1d5db', borderRadius: 6, background: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, color: '#374151' }}>
                              <Pencil size={13} /> Edit
                            </button>
                            <button onClick={() => handleDelete(emp.id)} style={{ padding: '5px 10px', border: '1px solid #fca5a5', borderRadius: 6, background: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, color: '#ef4444' }}>
                              <Trash2 size={13} /> Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {totalPages > 1 && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 20px', borderTop: '1px solid #e5e7eb' }}>
                    <span style={{ fontSize: 13, color: '#6b7280' }}>
                      Showing {(page - 1) * PER_PAGE + 1}–{Math.min(page * PER_PAGE, employees.length)} of {employees.length}
                    </span>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button className="page-btn" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}><ChevronLeft size={15} /></button>
                      {Array.from({ length: totalPages }, (_, i) => i + 1).map(n => (
                        <button key={n} className={`page-btn ${page === n ? 'page-active' : ''}`} onClick={() => setPage(n)}>{n}</button>
                      ))}
                      <button className="page-btn" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}><ChevronRight size={15} /></button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {modal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: '#fff', borderRadius: 12, padding: 28, width: 480, maxHeight: '90vh', overflowY: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>{editing ? 'Edit Employee' : 'Add Employee'}</h3>
              <button onClick={() => setModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280' }}><X size={20} /></button>
            </div>

            {saveError && (
              <div style={{ padding: '10px 14px', background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, color: '#dc2626', fontSize: 13, marginBottom: 16 }}>
                {saveError}
              </div>
            )}

            <form onSubmit={handleSave}>
              {[
                { label: 'First Name *', key: 'firstName', type: 'text', required: true },
                { label: 'Last Name',    key: 'lastName',  type: 'text' },
                { label: 'Employee Code *', key: 'employeeCode', type: 'text', required: true },
                { label: 'Email',  key: 'email', type: 'email' },
                { label: 'Phone',  key: 'phone', type: 'text' },
              ].map(f => (
                <div key={f.key} style={{ marginBottom: 14 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 5 }}>{f.label}</label>
                  <input
                    type={f.type}
                    required={f.required}
                    value={form[f.key]}
                    onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                    style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 7, fontSize: 14, boxSizing: 'border-box', outline: 'none' }}
                  />
                </div>
              ))}

              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 5 }}>Store *</label>
                <select
                  required
                  value={form.storeId}
                  onChange={e => setForm(p => ({ ...p, storeId: e.target.value }))}
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 7, fontSize: 14 }}
                >
                  <option value="">Select a store</option>
                  {stores.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>

              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 5 }}>Status</label>
                <select
                  value={form.status}
                  onChange={e => setForm(p => ({ ...p, status: e.target.value }))}
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 7, fontSize: 14 }}
                >
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="INACTIVE">INACTIVE</option>
                </select>
              </div>

              <div style={{ display: 'flex', gap: 10, marginTop: 22 }}>
                <button type="button" onClick={() => setModal(false)} style={{ flex: 1, padding: '10px', border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', fontSize: 14, cursor: 'pointer', fontWeight: 500 }}>
                  Cancel
                </button>
                <button type="submit" disabled={saving} style={{ flex: 1, padding: '10px', border: 'none', borderRadius: 8, background: saving ? '#93c5fd' : '#2563eb', color: '#fff', fontSize: 14, fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer' }}>
                  {saving ? 'Saving...' : editing ? 'Update' : 'Add Employee'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Employees;
