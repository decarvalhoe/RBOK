'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  CreateWebRTCSessionRequest,
  WebRTCConfigResponse,
  WebRTCSession,
  createWebRTCSession,
  getWebRTCConfig,
  getWebRTCSession,
  submitWebRTCCandidate,
} from '../../lib/api';

const POLL_INTERVAL_MS = 2500;

type ConnectionStatus =
  | 'idle'
  | 'requesting-media'
  | 'creating-offer'
  | 'waiting-answer'
  | 'answered'
  | 'closed'
  | 'error';

type StatusMessage = {
  label: string;
  tone: 'info' | 'success' | 'warning' | 'error';
};

const STATUS_COPY: Record<ConnectionStatus, StatusMessage> = {
  idle: { label: 'Prêt à initier une session', tone: 'info' },
  'requesting-media': { label: 'Autorisation caméra/micro en cours…', tone: 'info' },
  'creating-offer': { label: 'Génération de l’offre SDP…', tone: 'info' },
  'waiting-answer': { label: 'Session créée. En attente de la réponse distante…', tone: 'warning' },
  answered: { label: 'Session négociée, flux distant attendu.', tone: 'success' },
  closed: { label: 'Session clôturée.', tone: 'info' },
  error: { label: 'Une erreur est survenue.', tone: 'error' },
};

interface IceCandidatePayload {
  candidate: RTCIceCandidateInit;
}

function randomId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `client-${Math.random().toString(36).slice(2, 10)}`;
}

export default function WebRTCSessionPage(): JSX.Element {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [session, setSession] = useState<WebRTCSession | null>(null);
  const [iceServers, setIceServers] = useState<RTCIceServer[]>([]);
  const [clientId] = useState<string>(() => randomId());
  const localVideoRef = useRef<HTMLVideoElement | null>(null);
  const remoteVideoRef = useRef<HTMLVideoElement | null>(null);
  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const pendingCandidatesRef = useRef<RTCIceCandidateInit[]>([]);
  const localStreamRef = useRef<MediaStream | null>(null);
  const [remoteStream] = useState<MediaStream>(() => new MediaStream());

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const resetState = useCallback(() => {
    stopPolling();
    peerConnectionRef.current?.close();
    peerConnectionRef.current = null;
    localStreamRef.current?.getTracks().forEach((track) => track.stop());
    localStreamRef.current = null;
    setSession(null);
    sessionIdRef.current = null;
    pendingCandidatesRef.current = [];
    setConnectionStatus('idle');
    setErrorMessage(null);
  }, [stopPolling]);

  useEffect(() => {
    void (async () => {
      try {
        const config: WebRTCConfigResponse = await getWebRTCConfig();
        setIceServers(config.ice_servers as RTCIceServer[]);
      } catch (error) {
        console.error('Unable to fetch ICE configuration', error);
        setIceServers([]);
      }
    })();

    return () => {
      stopPolling();
      peerConnectionRef.current?.close();
      localStreamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [stopPolling]);

  useEffect(() => {
    if (remoteVideoRef.current && remoteStream) {
      remoteVideoRef.current.srcObject = remoteStream;
    }
  }, [remoteStream]);

  const pollForAnswer = useCallback(
    (sessionId: string) => {
      stopPolling();
      pollingRef.current = setInterval(async () => {
        try {
          const refreshed = await getWebRTCSession(sessionId);
          setSession(refreshed);
          sessionIdRef.current = refreshed.id;

          if (refreshed.answer_sdp && peerConnectionRef.current) {
            const description = new RTCSessionDescription({
              type: 'answer',
              sdp: refreshed.answer_sdp,
            });
            if (!peerConnectionRef.current.currentRemoteDescription) {
              await peerConnectionRef.current.setRemoteDescription(description);
              setConnectionStatus('answered');
            }
          }

          if (refreshed.status === 'closed') {
            setConnectionStatus('closed');
            stopPolling();
          }
        } catch (error) {
          console.error('Failed to refresh session', error);
          setErrorMessage('Impossible de récupérer la session.');
          setConnectionStatus('error');
          stopPolling();
        }
      }, POLL_INTERVAL_MS);
    },
    [stopPolling],
  );

  const sendCandidate = useCallback(async (sessionId: string, candidate: RTCIceCandidateInit) => {
    try {
      await submitWebRTCCandidate(sessionId, { candidate } satisfies IceCandidatePayload);
    } catch (error) {
      console.error('Failed to submit ICE candidate', error);
    }
  }, []);

  const startSession = useCallback(async () => {
    if (connectionStatus !== 'idle') {
      return;
    }

    setErrorMessage(null);
    setConnectionStatus('requesting-media');

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
      localStreamRef.current = stream;
      if (localVideoRef.current) {
        localVideoRef.current.srcObject = stream;
      }
    } catch (error) {
      console.error('Media permissions denied', error);
      setErrorMessage('Accès caméra/micro refusé.');
      setConnectionStatus('error');
      return;
    }

    setConnectionStatus('creating-offer');

    const peer = new RTCPeerConnection({ iceServers });
    peerConnectionRef.current = peer;

    peer.onicecandidate = (event) => {
      if (!event.candidate) {
        return;
      }

      const candidate = event.candidate.toJSON();
      const currentSessionId = sessionIdRef.current;
      if (currentSessionId) {
        void sendCandidate(currentSessionId, candidate);
      } else {
        pendingCandidatesRef.current.push(candidate);
      }
    };

    peer.ontrack = (event) => {
      event.streams[0]?.getTracks().forEach((track) => remoteStream.addTrack(track));
    };

    stream.getTracks().forEach((track) => peer.addTrack(track, stream));

    try {
      const offer = await peer.createOffer({
        offerToReceiveAudio: true,
        offerToReceiveVideo: true,
      });
      await peer.setLocalDescription(offer);

      const payload: CreateWebRTCSessionRequest = {
        client_id: clientId,
        offer_sdp: offer.sdp ?? '',
        metadata: { userAgent: navigator.userAgent },
      };
      const createdSession = await createWebRTCSession(payload);
      setSession(createdSession);
      sessionIdRef.current = createdSession.id;
      setConnectionStatus('waiting-answer');
      if (pendingCandidatesRef.current.length > 0) {
        for (const candidate of pendingCandidatesRef.current) {
          void sendCandidate(createdSession.id, candidate);
        }
        pendingCandidatesRef.current = [];
      }
      pollForAnswer(createdSession.id);
    } catch (error) {
      console.error('Failed to negotiate session', error);
      setErrorMessage("Impossible de créer l'offre WebRTC.");
      setConnectionStatus('error');
    }
  }, [clientId, connectionStatus, iceServers, pollForAnswer, sendCandidate, remoteStream]);

  const closeSession = useCallback(() => {
    resetState();
  }, [resetState]);

  const status = useMemo(() => STATUS_COPY[connectionStatus], [connectionStatus]);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
      <header className="space-y-2">
        <p
          className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ${
            status.tone === 'success'
              ? 'bg-emerald-100 text-emerald-800'
              : status.tone === 'warning'
                ? 'bg-amber-100 text-amber-800'
                : status.tone === 'error'
                  ? 'bg-rose-100 text-rose-800'
                  : 'bg-blue-100 text-blue-800'
          }`}
        >
          {status.label}
        </p>
        <h1 className="text-3xl font-semibold text-slate-900">Session WebRTC expérimentale</h1>
        <p className="text-sm text-slate-600">
          Démarrez une session en initiant une offre SDP et partagez l’identifiant avec un second
          poste pour compléter la négociation.
        </p>
      </header>

      {errorMessage ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          {errorMessage}
        </div>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <h2 className="text-lg font-medium text-slate-800">Flux local</h2>
          <video
            ref={localVideoRef}
            className="aspect-video w-full rounded-lg bg-slate-900 object-cover"
            playsInline
            autoPlay
            muted
          />
        </div>
        <div className="space-y-2">
          <h2 className="text-lg font-medium text-slate-800">Flux distant</h2>
          <video
            ref={remoteVideoRef}
            className="aspect-video w-full rounded-lg bg-slate-900 object-cover"
            playsInline
            autoPlay
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Coordonnées de session</h2>
        <dl className="grid gap-2 text-sm text-slate-600">
          <div>
            <dt className="font-medium text-slate-800">Identifiant session</dt>
            <dd className="break-all font-mono text-xs text-slate-500">
              {session?.id ?? 'Non disponible'}
            </dd>
          </div>
          <div>
            <dt className="font-medium text-slate-800">Identifiant client</dt>
            <dd className="break-all font-mono text-xs text-slate-500">{clientId}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-800">Serveurs ICE configurés</dt>
            <dd className="font-mono text-xs text-slate-500">
              {iceServers.length > 0
                ? iceServers.map((server) => server.urls.join(', ')).join(' | ')
                : 'Aucun serveur configuré'}
            </dd>
          </div>
        </dl>
      </section>

      <section className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => void startSession()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
          disabled={connectionStatus !== 'idle'}
        >
          Démarrer une session
        </button>
        <button
          type="button"
          onClick={closeSession}
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={connectionStatus === 'idle'}
        >
          Réinitialiser
        </button>
      </section>

      <section className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Instructions de test manuel</h2>
        <ol className="list-decimal space-y-2 pl-5">
          <li>Démarrez une session depuis ce navigateur et copiez l’identifiant affiché.</li>
          <li>
            Depuis un autre poste (ou un navigateur différent), appelez l’API
            <code className="mx-1 rounded bg-slate-100 px-1 py-0.5">/webrtc/sessions/{{ id }}</code>
            pour récupérer l’offre et répondre avec <code className="mx-1">/answer</code>.
          </li>
          <li>
            Une fois la réponse envoyée, surveillez l’état de la session : le statut « answered »
            confirme la négociation et le flux distant devrait apparaître.
          </li>
        </ol>
      </section>
    </main>
  );
}
