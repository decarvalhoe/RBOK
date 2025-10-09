import { readJSON, storage, storageKeys, writeJSON } from './mmkv';

export type ConversationMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
};

export type ConversationSession = {
  runId: string;
  procedureId: string;
  messages: ConversationMessage[];
};

type SessionDictionary = Record<string, ConversationSession>;

const getSessions = (): SessionDictionary =>
  readJSON<SessionDictionary>(storageKeys.sessions, {});

export const getSession = (runId: string): ConversationSession | null => {
  const sessions = getSessions();
  return sessions[runId] ?? null;
};

export const upsertSession = (session: ConversationSession) => {
  const sessions = getSessions();
  sessions[session.runId] = session;
  writeJSON(storageKeys.sessions, sessions);
};

export const appendMessage = (
  runId: string,
  message: ConversationMessage,
  procedureId?: string
): ConversationSession => {
  const session = getSession(runId) ?? {
    runId,
    procedureId: procedureId ?? 'unknown',
    messages: [],
  };

  const updated: ConversationSession = {
    ...session,
    procedureId: procedureId ?? session.procedureId,
    messages: [...session.messages, message],
  };
  upsertSession(updated);
  return updated;
};

export const clearSessions = () => {
  storage.delete(storageKeys.sessions);
};
