/**
 * WebSocket hook for live holographic reconstruction updates
 * Production-ready with:
 * - Exponential backoff reconnection
 * - Heartbeat/ping-pong for connection health
 * - Message queuing during disconnect
 * - File watcher integration on backend
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { VisualizationResponse } from "../types";

export interface HolographicStreamMessage {
  type: "reconstruction_update" | "connected" | "error" | "pong" | "evidence_added" | "config_change";
  incident_id: string;
  data?: VisualizationResponse;
  evidence_count?: number;
  timestamp?: number;
  message?: string;
  evidence_info?: {
    file_path: string;
    file_type: string;
    size_bytes: number;
  };
}

export interface UseHolographicStreamOptions {
  incidentId: string;
  autoConnect?: boolean;
  onUpdate?: (data: VisualizationResponse) => void;
  onEvidenceAdded?: (info: { file_path: string; file_type: string }) => void;
  onError?: (error: string) => void;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  heartbeatInterval?: number;
}

export interface UseHolographicStreamReturn {
  isConnected: boolean;
  lastData: VisualizationResponse | null;
  lastError: string | null;
  evidenceCount: number;
  connectionQuality: "excellent" | "good" | "degraded" | "disconnected";
  connect: () => void;
  disconnect: () => void;
  sendPing: () => void;
  sendMessage: (message: object) => void;
}

export function useHolographicStream(options: UseHolographicStreamOptions): UseHolographicStreamReturn {
  const {
    incidentId,
    autoConnect = true,
    onUpdate,
    onEvidenceAdded,
    onError,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
    heartbeatInterval = 30000,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastData, setLastData] = useState<VisualizationResponse | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const [evidenceCount, setEvidenceCount] = useState(0);
  const [connectionQuality, setConnectionQuality] = useState<"excellent" | "good" | "degraded" | "disconnected">("disconnected");

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const heartbeatTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastPongRef = useRef<number>(0);
  const mountedRef = useRef(true);
  const messageQueueRef = useRef<Array<{ type: string; payload: any }>>([]);

  // Caller callbacks live in refs: `connect`'s useCallback deps used to
  // include them, so any consumer passing inline lambdas (a new function
  // identity every render) tore the socket down and reconnected on EVERY
  // render via the mount effect.
  const onUpdateRef = useRef(onUpdate);
  const onEvidenceAddedRef = useRef(onEvidenceAdded);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onUpdateRef.current = onUpdate;
    onEvidenceAddedRef.current = onEvidenceAdded;
    onErrorRef.current = onError;
  });

  const getWsUrl = useCallback(() => {
    // Next.js provides no `import.meta.env` (Vite-only). Derive the WebSocket
    // URL from the same API base chain as lib/api.ts (http->ws), with an
    // optional explicit WS host override. The base already includes /v1.
    const apiBase =
      process.env.NEXT_PUBLIC_API_URL ||
      process.env.NEXT_PUBLIC_BACKEND_URL ||
      "http://localhost:8000/api/v1";
    const wsBase = process.env.NEXT_PUBLIC_API_WS_HOST
      ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${process.env.NEXT_PUBLIC_API_WS_HOST}`
      : apiBase.replace(/^http/, "ws");
    return `${wsBase}/holographic/stream/${incidentId}`;
  }, [incidentId]);

  const startHeartbeat = useCallback(() => {
    if (heartbeatTimeoutRef.current) {
      clearTimeout(heartbeatTimeoutRef.current);
    }
    heartbeatTimeoutRef.current = setTimeout(() => {
      sendPing();
      // Check if pong received recently
      const now = Date.now();
      const timeSincePong = now - lastPongRef.current;
      if (timeSincePong > heartbeatInterval * 2) {
        // Hung socket: no pong for two heartbeat periods (dead peer with a
        // still-OPEN TCP connection stays OPEN for a long time). The old code
        // only downgraded the quality badge and never repaired anything.
        // Detach, close, and let the socket's own onclose drive the
        // reconnect (attempt counting + backoff stay in one place). The
        // browser force-closes a close() that gets no ack, so onclose is
        // guaranteed to fire even against a dead peer.
        setConnectionQuality("disconnected");
        const ws = wsRef.current;
        wsRef.current = null;
        if (ws) {
          try {
            ws.close();
          } catch {
            // already closing/closed — nothing to salvage
          }
        }
        // Do NOT reschedule: onopen -> startHeartbeat() resumes the loop
        // after the reconnect.
        return;
      }
      if (timeSincePong > heartbeatInterval) {
        setConnectionQuality("good");
      } else {
        setConnectionQuality("excellent");
      }
      startHeartbeat();
    }, heartbeatInterval);
  }, [heartbeatInterval]);

  const connect = useCallback(() => {
    // Guard CONNECTING as well as OPEN: while the first socket was still
    // handshaking, repeated calls (mount effect + consumer) slipped past the
    // OPEN-only guard and leaked a second websocket.
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    const url = getWsUrl();
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) {
        ws.close();
        return;
      }
      setIsConnected(true);
      setLastError(null);
      setConnectionQuality("excellent");
      reconnectAttemptsRef.current = 0;
      lastPongRef.current = Date.now();
      startHeartbeat();

      // Flush message queue
      while (messageQueueRef.current.length > 0) {
        const msg = messageQueueRef.current.shift();
        if (msg && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify(msg));
        }
      }
    };

    ws.onmessage = (event) => {
      try {
        const message: HolographicStreamMessage = JSON.parse(event.data);

        switch (message.type) {
          case "reconstruction_update":
            if (message.data) {
              setLastData(message.data);
              setEvidenceCount(message.evidence_count || 0);
              onUpdateRef.current?.(message.data);
            }
            break;
          case "evidence_added":
            setEvidenceCount(message.evidence_count || 0);
            onEvidenceAddedRef.current?.({
              file_path: message.evidence_info?.file_path || "unknown",
              file_type: message.evidence_info?.file_type || "unknown",
            });
            break;
          case "error":
            setLastError(message.message || "Unknown error");
            onErrorRef.current?.(message.message || "Unknown error");
            break;
          case "connected":
            console.log(`Holographic stream connected: ${message.message}`);
            break;
          case "pong":
            lastPongRef.current = Date.now();
            setConnectionQuality("excellent");
            break;
        }
      } catch (err) {
        console.error("Failed to parse WebSocket message:", err);
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;

      setIsConnected(false);
      setConnectionQuality("disconnected");
      if (heartbeatTimeoutRef.current) {
        clearTimeout(heartbeatTimeoutRef.current);
      }

      // Attempt reconnection
      if (reconnectAttemptsRef.current < maxReconnectAttempts) {
        reconnectAttemptsRef.current++;
        // True exponential backoff (3s, 6s, 12s, 24s, 48s, then capped at
        // 96s) — the old `interval * min(attempts, 5)` was linear despite
        // commenting itself as exponential.
        const delay = reconnectInterval * Math.pow(2, Math.min(reconnectAttemptsRef.current - 1, 5));

        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      } else {
        const errMsg = `Max reconnection attempts (${maxReconnectAttempts}) reached`;
        setLastError(errMsg);
        onErrorRef.current?.(errMsg);
      }
    };

    ws.onerror = (event) => {
      console.error("WebSocket error:", event);
      setLastError("WebSocket connection error");
      onErrorRef.current?.("WebSocket connection error");
    };
  }, [getWsUrl, maxReconnectAttempts, reconnectInterval, startHeartbeat]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (heartbeatTimeoutRef.current) {
      clearTimeout(heartbeatTimeoutRef.current);
      heartbeatTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setConnectionQuality("disconnected");
  }, []);

  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "ping" }));
    }
  }, []);

  const sendMessage = useCallback((message: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      // Queue for when connection restores
      messageQueueRef.current.push({ type: "custom", payload: message });
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;

    if (autoConnect) {
      connect();
    }

    return () => {
      mountedRef.current = false;
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  return {
    isConnected,
    lastData,
    lastError,
    evidenceCount,
    connectionQuality,
    connect,
    disconnect,
    sendPing,
    sendMessage,
  };
}