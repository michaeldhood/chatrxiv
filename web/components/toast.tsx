"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type ToastVariant = "success" | "error" | "info";

interface ToastOptions {
  title: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
}

interface ToastRecord extends Required<Omit<ToastOptions, "duration">> {
  id: string;
  duration: number;
  isLeaving: boolean;
}

interface ToastContextValue {
  addToast: (options: ToastOptions) => void;
  pushToast: (options: ToastOptions) => void;
  showToast: (options: ToastOptions) => void;
  dismissToast: (id: string) => void;
  success: (title: string, description?: string, duration?: number) => void;
  error: (title: string, description?: string, duration?: number) => void;
  info: (title: string, description?: string, duration?: number) => void;
}

const TOAST_DURATION_MS = 5000;
const LEAVE_ANIMATION_MS = 220;

const ToastContext = createContext<ToastContextValue | null>(null);

function getVariantClasses(variant: ToastVariant): string {
  switch (variant) {
    case "success":
      return "border-accent-green/40 bg-accent-green/10 text-accent-green";
    case "error":
      return "border-destructive/40 bg-destructive/10 text-destructive";
    default:
      return "border-primary/40 bg-primary/10 text-primary";
  }
}

function getVariantIcon(variant: ToastVariant): string {
  switch (variant) {
    case "success":
      return "✓";
    case "error":
      return "!";
    default:
      return "i";
  }
}

export function ToastProvider({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);
  const timeoutRefs = useRef<Map<string, number>>(new Map());

  const clearToastTimeout = useCallback((id: string) => {
    const timeout = timeoutRefs.current.get(id);
    if (timeout) {
      window.clearTimeout(timeout);
      timeoutRefs.current.delete(id);
    }
  }, []);

  const removeToast = useCallback(
    (id: string) => {
      clearToastTimeout(id);
      setToasts((current) => current.filter((toast) => toast.id !== id));
    },
    [clearToastTimeout]
  );

  const dismissToast = useCallback(
    (id: string) => {
      clearToastTimeout(id);
      setToasts((current) =>
        current.map((toast) =>
          toast.id === id ? { ...toast, isLeaving: true } : toast
        )
      );

      const leaveTimeout = window.setTimeout(() => {
        removeToast(id);
      }, LEAVE_ANIMATION_MS);
      timeoutRefs.current.set(id, leaveTimeout);
    },
    [clearToastTimeout, removeToast]
  );

  const showToast = useCallback(
    ({
      title,
      description = "",
      variant = "info",
      duration = TOAST_DURATION_MS,
    }: ToastOptions) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

      setToasts((current) => [
        ...current,
        {
          id,
          title,
          description,
          variant,
          duration,
          isLeaving: false,
        },
      ]);

      const timeout = window.setTimeout(() => {
        dismissToast(id);
      }, duration);
      timeoutRefs.current.set(id, timeout);
    },
    [dismissToast]
  );

  useEffect(() => {
    const activeTimeouts = timeoutRefs.current;
    return () => {
      activeTimeouts.forEach((timeout) => window.clearTimeout(timeout));
      activeTimeouts.clear();
    };
  }, []);

  const value = useMemo<ToastContextValue>(
    () => ({
      addToast: showToast,
      pushToast: showToast,
      showToast,
      dismissToast,
      success: (title, description, duration) =>
        showToast({ title, description, duration, variant: "success" }),
      error: (title, description, duration) =>
        showToast({ title, description, duration, variant: "error" }),
      info: (title, description, duration) =>
        showToast({ title, description, duration, variant: "info" }),
    }),
    [dismissToast, showToast]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed top-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-3">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`pointer-events-auto overflow-hidden rounded-xl border shadow-2xl backdrop-blur-sm transition-all duration-200 ${
              toast.isLeaving
                ? "translate-x-6 opacity-0"
                : "translate-x-0 opacity-100"
            } ${getVariantClasses(toast.variant)}`}
          >
            <div className="bg-card/90 px-4 py-3">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-current/20 bg-current/10 text-sm font-semibold">
                  {getVariantIcon(toast.variant)}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-foreground">
                    {toast.title}
                  </p>
                  {toast.description && (
                    <p className="mt-1 text-sm text-muted-foreground">
                      {toast.description}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => dismissToast(toast.id)}
                  className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  aria-label="Dismiss notification"
                >
                  ×
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
