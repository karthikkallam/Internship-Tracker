import { useState } from 'react';
import * as Toast from '@radix-ui/react-toast';
import { ToastMessage } from '../types';

interface NotificationToastProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

const ToastItem = ({ toast, onDismiss }: { toast: ToastMessage; onDismiss: (id: string) => void }) => {
  const [open, setOpen] = useState(true);

  const handleOpenChange = (value: boolean) => {
    setOpen(value);
    if (!value) {
      onDismiss(toast.id);
    }
  };

  return (
    <Toast.Root
      open={open}
      onOpenChange={handleOpenChange}
      duration={6000}
      className="w-80 rounded-xl border border-slate-700 bg-slate-900/95 p-4 shadow-lg shadow-brand-900/30 backdrop-blur"
    >
      <Toast.Title className="text-sm font-semibold text-brand-200">{toast.title}</Toast.Title>
      {toast.description && (
        <Toast.Description className="mt-1 text-xs text-slate-300">
          {toast.description}
        </Toast.Description>
      )}
      {toast.url && (
        <a
          href={toast.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-flex text-xs font-semibold text-brand-300 underline"
        >
          View listing
        </a>
      )}
      <Toast.Close className="absolute right-2 top-2 text-slate-500 transition hover:text-brand-300">
        ×
      </Toast.Close>
    </Toast.Root>
  );
};

export function NotificationToast({ toasts, onDismiss }: NotificationToastProps) {
  return (
    <Toast.Provider swipeDirection="right">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
      <Toast.Viewport className="fixed top-4 right-4 z-50 flex max-h-screen w-96 flex-col gap-3 outline-none" />
    </Toast.Provider>
  );
}

export default NotificationToast;
