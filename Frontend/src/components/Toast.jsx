import { createContext, useContext, useState, useCallback } from 'react';

const ToastCtx = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const show = useCallback((message, type = 'success') => {
    const id = Date.now() + Math.random();
    setToasts(p => [...p, { id, message, type }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 3500);
  }, []);

  const remove = (id) => setToasts(p => p.filter(t => t.id !== id));

  return (
    <ToastCtx.Provider value={show}>
      {children}
      <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 9999, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {toasts.map(t => (
          <div key={t.id} onClick={() => remove(t.id)} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '12px 18px', borderRadius: 10, cursor: 'pointer',
            fontSize: 14, fontWeight: 500, minWidth: 260, maxWidth: 380,
            boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
            background: t.type === 'error' ? '#fef2f2' : t.type === 'warning' ? '#fffbeb' : '#f0fdf4',
            color: t.type === 'error' ? '#dc2626' : t.type === 'warning' ? '#d97706' : '#16a34a',
            border: `1px solid ${t.type === 'error' ? '#fca5a5' : t.type === 'warning' ? '#fcd34d' : '#86efac'}`,
            animation: 'slideIn .25s ease',
          }}>
            <span style={{ fontSize: 18 }}>
              {t.type === 'error' ? '✕' : t.type === 'warning' ? '⚠' : '✓'}
            </span>
            <span style={{ flex: 1 }}>{t.message}</span>
          </div>
        ))}
      </div>
      <style>{`@keyframes slideIn{from{transform:translateX(60px);opacity:0}to{transform:translateX(0);opacity:1}}`}</style>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
