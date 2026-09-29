"use client";

import { useEffect, useState } from "react";

type NotificationType = "success" | "error" | "info" | "warning";

interface Notification {
  id: number;
  message: string;
  type: NotificationType;
  duration?: number;
}

let notificationId = 0;

// Global state for notifications using a mutable array
const notifications: Notification[] = [];
let listeners: ((notifications: Notification[]) => void)[] = [];

// Notify function that properly adds notifications
export const notify = (message: string, type: NotificationType = "info", duration: number = 5000) => {
  const notification: Notification = {
    id: ++notificationId,
    message,
    type,
    duration,
  };

  notifications.push(notification);
  listeners.forEach(listener => listener([...notifications]));

  // Auto-remove after duration
  setTimeout(() => {
    const index = notifications.findIndex(n => n.id === notification.id);
    if (index !== -1) {
      notifications.splice(index, 1);
    }
    listeners.forEach(listener => listener([...notifications]));
  }, duration);
};

export function NotificationContainer() {
  const [notificationsState, setNotificationsState] = useState<Notification[]>([]);

  useEffect(() => {
    const listener = (newNotifications: Notification[]) => {
      setNotificationsState([...newNotifications]);
    };

    listeners.push(listener);

    // Initial call to populate any existing notifications
    listener([...notifications]);

    return () => {
      listeners = listeners.filter(l => l !== listener);
    };
  }, []);

  const removeNotification = (id: number) => {
    const index = notifications.findIndex(n => n.id === id);
    if (index !== -1) {
      notifications.splice(index, 1);
    }
    listeners.forEach(listener => listener([...notifications]));
  };

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full">
      {notificationsState.map(notification => (
        <div
          key={notification.id}
          className="flex items-center gap-3 p-4 rounded-lg border shadow-lg backdrop-blur-sm"
          style={{
            backgroundColor: "rgba(255, 255, 255, 0.05)",
            border: "1px solid rgba(255, 255, 255, 0.1)",
          }}
        >
          <div className="flex-shrink-0">
            {notification.type === "success" ? (
              <svg className="w-5 h-5 text-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : notification.type === "error" ? (
              <svg className="w-5 h-5 text-danger" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : notification.type === "warning" ? (
              <svg className="w-5 h-5 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            ) : (
              <div className="w-5 h-5 bg-primary/20 rounded-full" />
            )}
          </div>
          <div className="flex-1">
            <p className="text-sm text-foreground">{notification.message}</p>
          </div>
        </div>
      ))}
    </div>
  );
}