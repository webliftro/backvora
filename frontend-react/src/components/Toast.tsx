import { useState, useCallback, createContext, useContext, type ReactNode } from 'react';
import { X, CheckCircle2, AlertCircle, AlertTriangle, Info, type LucideIcon } from 'lucide-react';

type ToastType = 'success' | 'error' | 'warning' | 'info';

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastCtx {
  toast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastCtx>({ toast: () => {} });

export const useToast = () => useContext(ToastContext);

let nextId = 0;

const toastStyles: Record<ToastType, { icon: LucideIcon; accent: string }> = {
  success: { icon: CheckCircle2, accent: 'text-green-400 border-green-600/40' },
  error: { icon: AlertCircle, accent: 'text-red-400 border-red-600/40' },
  warning: { icon: AlertTriangle, accent: 'text-yellow-400 border-yellow-600/40' },
  info: { icon: Info, accent: 'text-teal-400 border-teal-600/40' },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((message: string, type: ToastType = 'success') => {
    const id = nextId++;
    setToasts(prev => [...prev, { id, message, type }]);
    const duration = type === 'error' ? 8000 : type === 'warning' ? 6000 : 5000;
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), duration);
  }, []);

  const remove = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 space-y-2 z-50">
        {toasts.map(t => {
          const { icon: Icon, accent } = toastStyles[t.type];
          return (
            <div key={t.id} className={`glass border ${accent} text-gray-100 px-4 py-3 rounded-lg max-w-md flex items-start gap-2.5`}>
              <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${accent.split(' ')[0]}`} />
              <span className="whitespace-pre-line flex-1 text-sm">{t.message}</span>
              <button onClick={() => remove(t.id)} className="shrink-0 mt-0.5 text-gray-500 hover:text-gray-200 transition-colors" aria-label="Dismiss notification"><X className="w-4 h-4" /></button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
