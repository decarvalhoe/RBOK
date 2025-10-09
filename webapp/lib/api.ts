import axios, { AxiosInstance } from 'axios';

export interface ChatResponse {
  role: string;
  content: string;
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

export default client;
