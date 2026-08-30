import { useState, useEffect, useRef } from 'react';
import api from '../api/client';

export function useAgentEvents(projectId, isAnalyzing) {
  const [events, setEvents] = useState([]);
  const [isLive, setIsLive] = useState(false);
  const [currentTool, setCurrentTool] = useState(null);
  const [agentStatus, setAgentStatus] = useState('idle'); // idle | running | completed | error
  const [errorMessage, setErrorMessage] = useState(null);
  const eventSourceRef = useRef(null);
  const pollIntervalRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);

  useEffect(() => {
    if (!projectId || !isAnalyzing) return;

    setAgentStatus('running');
    setErrorMessage(null);
    reconnectAttemptsRef.current = 0;

    // Load initial events from history
    api.getEvents(projectId).then(initialEvents => {
      if (initialEvents && initialEvents.length > 0) {
        setEvents(initialEvents);
        const last = initialEvents[initialEvents.length - 1];
        if (last?.type === 'AGENT_ERROR') {
          setAgentStatus('error');
          setErrorMessage(last.summary || 'An error occurred during agent execution.');
        } else if (['AGENT_COMPLETED', 'VERIFICATION_COMPLETED'].includes(last?.type)) {
          setAgentStatus('completed');
        }
      }
    }).catch(err => console.error('Failed to load initial events:', err));

    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    const sseUrl = `${apiBaseUrl}/api/projects/${projectId}/events/stream`;

    function connectSSE() {
      try {
        const es = new EventSource(sseUrl);
        eventSourceRef.current = es;

        es.onopen = () => {
          setIsLive(true);
          reconnectAttemptsRef.current = 0;
        };

        es.onmessage = (e) => {
          try {
            const data = JSON.parse(e.data);
            if (data.type === 'CONNECTED' || data.type === 'HEARTBEAT') return;

            setEvents((prev) => {
              // Deduplicate events by event_id or signature
              const isDuplicate = prev.some(item => 
                (item.event_id && data.event_id && item.event_id === data.event_id) ||
                (item.timestamp === data.timestamp && item.type === data.type && item.summary === data.summary)
              );
              if (isDuplicate) return prev;
              return [...prev, data];
            });

            if (data.tool) {
              setCurrentTool(data.tool);
            }

            if (data.type === 'AGENT_COMPLETED' || data.type === 'VERIFICATION_COMPLETED') {
              setAgentStatus('completed');
              setIsLive(false);
              es.close();
            } else if (data.type === 'AGENT_ERROR') {
              setAgentStatus('error');
              setErrorMessage(data.summary || 'Agent encountered an error.');
              setIsLive(false);
              es.close();
            }
          } catch (err) {
            console.error('Failed to parse SSE message:', err);
          }
        };

        es.onerror = (err) => {
          setIsLive(false);
          es.close();
          if (reconnectAttemptsRef.current < 3) {
            reconnectAttemptsRef.current += 1;
            const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 5000);
            setTimeout(connectSSE, delay);
          } else {
            startPolling();
          }
        };
      } catch (err) {
        startPolling();
      }
    }

    connectSSE();

    function startPolling() {
      if (pollIntervalRef.current) return;
      pollIntervalRef.current = setInterval(async () => {
        try {
          const latestEvents = await api.getEvents(projectId);
          if (latestEvents) {
            setEvents(latestEvents);
            const lastEvent = latestEvents[latestEvents.length - 1];
            if (lastEvent) {
              if (lastEvent.tool) setCurrentTool(lastEvent.tool);
              if (['AGENT_COMPLETED', 'VERIFICATION_COMPLETED'].includes(lastEvent.type)) {
                setAgentStatus('completed');
                clearInterval(pollIntervalRef.current);
              } else if (lastEvent.type === 'AGENT_ERROR') {
                setAgentStatus('error');
                setErrorMessage(lastEvent.summary || 'Agent execution failed.');
                clearInterval(pollIntervalRef.current);
              }
            }
          }
        } catch (pollErr) {
          console.error('Polling error:', pollErr);
        }
      }, 2000);
    }

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [projectId, isAnalyzing]);

  return { events, isLive, currentTool, agentStatus, errorMessage };
}
