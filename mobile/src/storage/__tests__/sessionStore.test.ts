import {
  appendMessage,
  clearSessions,
  getSession,
  upsertSession,
  ConversationMessage,
  ConversationSession,
} from '../sessionStore';
import { storage, storageKeys } from '../mmkv';

describe('session store', () => {
  beforeEach(() => {
    clearSessions();
    storage.delete(storageKeys.cachedSteps);
  });

  it('returns null when session missing', () => {
    expect(getSession('missing')).toBeNull();
  });

  it('upserts and retrieves sessions', () => {
    const session: ConversationSession = {
      runId: 'run-1',
      procedureId: 'proc-1',
      messages: [],
    };

    upsertSession(session);

    expect(getSession('run-1')).toEqual(session);
  });

  it('appends messages to existing session', () => {
    const base: ConversationSession = {
      runId: 'run-1',
      procedureId: 'proc-1',
      messages: [],
    };

    upsertSession(base);

    const message: ConversationMessage = {
      id: 'msg-1',
      role: 'user',
      content: 'Bonjour',
      createdAt: '2024-01-01T00:00:00.000Z',
    };

    const updated = appendMessage('run-1', message);

    expect(updated.messages).toHaveLength(1);
    expect(getSession('run-1')?.messages[0]).toEqual(message);
  });

  it('creates session when missing on append', () => {
    const message: ConversationMessage = {
      id: 'msg-1',
      role: 'assistant',
      content: 'Bonjour',
      createdAt: '2024-01-01T00:00:00.000Z',
    };

    const session = appendMessage('run-2', message, 'proc-2');

    expect(session.procedureId).toBe('proc-2');
    expect(session.messages).toEqual([message]);
  });

  it('clears sessions from storage', () => {
    upsertSession({ runId: 'run-1', procedureId: 'proc-1', messages: [] });
    clearSessions();
    expect(getSession('run-1')).toBeNull();
  });
});
