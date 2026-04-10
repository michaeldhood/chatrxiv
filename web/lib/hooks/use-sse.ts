"use client";

import { useEffect, useRef } from 'react';
import { useToast } from '@/components/toast';

/**
 * Hook for Server-Sent Events (SSE) connection.
 * 
 * Automatically connects to the SSE endpoint and calls onUpdate when updates are received.
 * Handles reconnection on errors.
 */
export function useSSE(url: string, onUpdate: () => void) {
  const onUpdateRef = useRef(onUpdate);
  const { showToast } = useToast();
  const parseErrorShownRef = useRef(false);
  
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
        if (!parseErrorShownRef.current) {
          parseErrorShownRef.current = true;
          showToast({
            variant: 'error',
            title: 'Live updates failed',
            description: 'Received an invalid update payload from the server.',
          });
        }
      }
    };
    
    source.onerror = (error) => {
      console.debug('SSE connection error, will reconnect automatically:', error);
      // EventSource automatically reconnects
    };
    
    return () => {
      source.close();
    };
  }, [showToast, url]);
}
