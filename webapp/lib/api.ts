import axios, { AxiosInstance } from 'axios';

export interface ChatResponse {
  role: string;
  content: string;
}

export interface IceServer {
  urls: string[];
  username?: string;
  credential?: string;
}

export interface WebRTCSession {
  id: string;
  client_id: string;
  responder_id?: string | null;
  status: string;
  offer_sdp: string;
  answer_sdp?: string | null;
  metadata: Record<string, unknown>;
  responder_metadata: Record<string, unknown>;
  ice_candidates: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
}

export interface CreateWebRTCSessionRequest {
  client_id: string;
  offer_sdp: string;
  metadata?: Record<string, unknown>;
}

export interface SubmitAnswerRequest {
  responder_id: string;
  answer_sdp: string;
  responder_metadata?: Record<string, unknown>;
}

export interface SubmitCandidateRequest {
  candidate: Record<string, unknown>;
}

export interface WebRTCConfigResponse {
  ice_servers: IceServer[];
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

const client: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function sendChatMessage(message: string): Promise<ChatResponse> {
  const { data } = await client.post<ChatResponse>('/chat', { message });
  return data;
}

export async function getWebRTCConfig(): Promise<WebRTCConfigResponse> {
  const { data } = await client.get<WebRTCConfigResponse>('/webrtc/config');
  return data;
}

export async function createWebRTCSession(
  payload: CreateWebRTCSessionRequest,
): Promise<WebRTCSession> {
  const { data } = await client.post<WebRTCSession>('/webrtc/sessions', payload);
  return data;
}

export async function getWebRTCSession(sessionId: string): Promise<WebRTCSession> {
  const { data } = await client.get<WebRTCSession>(`/webrtc/sessions/${sessionId}`);
  return data;
}

export async function submitWebRTCAnswer(
  sessionId: string,
  payload: SubmitAnswerRequest,
): Promise<WebRTCSession> {
  const { data } = await client.post<WebRTCSession>(
    `/webrtc/sessions/${sessionId}/answer`,
    payload,
  );
  return data;
}

export async function submitWebRTCCandidate(
  sessionId: string,
  payload: SubmitCandidateRequest,
): Promise<WebRTCSession> {
  const { data } = await client.post<WebRTCSession>(
    `/webrtc/sessions/${sessionId}/candidates`,
    payload,
  );
  return data;
}

export default client;
