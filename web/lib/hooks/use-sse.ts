"use client";

import { useEffect, useRef } from 'react';

/**
 * Hook for Server-Sent Events (SSE) connection.
 * 
 * Automatically connects to the SSE endpoint and calls onUpdate when updates are received.
 * Handles reconnection on errors.
 */
export function useSSE(url: string, onUpdate: () => void) {
  const onUpdateRef = useRef(onUpdate);
  
  // Keep callback ref up to date
  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);
  
  useEffect(() => {
    if (typeof window === 'undefined' || typeof EventSource === 'undefined') {
      return;
    }
    
    const source = new EventSource(url);
    
    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'update' || data.type === 'connected') {
          onUpdateRef.current();
        }
      } catch (error) {
        console.error('Failed to parse SSE message:', error);
      }
    };
    
    source.onerror = (error) => {
      console.debug('SSE connection error, will reconnect automatically:', error);
      // EventSource automatically reconnects
    };
    
    return () => {
      source.close();
    };
  }, [url]);
}
