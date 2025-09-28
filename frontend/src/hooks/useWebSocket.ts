import { useEffect, useRef, useState } from 'react';

type UseWebSocketOptions = {
  onMessage?: (event: MessageEvent) => void;
  shouldReconnect?: boolean;
  reconnectInterval?: number;
};

const normalizeUrl = (endpoint: string): string => {
  if (endpoint.startsWith('ws')) {
    return endpoint;
  }
  if (endpoint.startsWith('http')) {
    return endpoint.replace(/^http/i, 'ws');
  }
  return `ws://${endpoint}`;
};

export const useWebSocket = (
  url: string,
  { onMessage, shouldReconnect = true, reconnectInterval = 5000 }: UseWebSocketOptions = {}
) => {
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number>();
  const callbackRef = useRef<UseWebSocketOptions['onMessage']>(onMessage);
  const [readyState, setReadyState] = useState<WebSocket['readyState']>(WebSocket.CLOSED);

  useEffect(() => {
    callbackRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      const socketUrl = normalizeUrl(url);
      const socket = new WebSocket(socketUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        if (!cancelled) {
          setReadyState(socket.readyState);
        }
      };

      socket.onclose = () => {
        if (!cancelled) {
          setReadyState(WebSocket.CLOSED);
          if (shouldReconnect) {
            reconnectTimerRef.current = window.setTimeout(connect, reconnectInterval);
          }
        }
      };

      socket.onerror = () => {
        socket.close();
      };

      socket.onmessage = (event) => {
        callbackRef.current?.(event);
      };
    };

    connect();

    return () => {
      cancelled = true;
      const ws = socketRef.current;
      socketRef.current = null;
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      ws?.close();
    };
  }, [url, reconnectInterval, shouldReconnect]);

  const send = (data: unknown) => {
    const ws = socketRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  };

  return { readyState, send };
};
