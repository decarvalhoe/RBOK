import { appendMessage, clearSessions, getSession, upsertSession } from '../sessionStore';
import { readJSON, storage, storageKeys, writeJSON } from '../mmkv';

jest.mock('../mmkv', () => ({
  readJSON: jest.fn(),
  writeJSON: jest.fn(),
  storage: { delete: jest.fn() },
  storageKeys: { sessions: 'sessions', cachedSteps: 'cached-steps' },
}));

const mockedReadJSON = readJSON as jest.Mock;
const mockedWriteJSON = writeJSON as jest.Mock;
const mockedStorageDelete = storage.delete as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
});

afterEach(() => {
  jest.clearAllMocks();
});

afterAll(() => {
  jest.resetModules();
});

describe('sessionStore', () => {
  it('hydrates an existing session from storage', () => {
    const session = {
      runId: 'run-1',
      procedureId: 'proc-1',
      messages: [],
    };
    mockedReadJSON.mockReturnValueOnce({ 'run-1': session });

    expect(getSession('run-1')).toEqual(session);
    expect(mockedReadJSON).toHaveBeenCalledWith(storageKeys.sessions, {});
  });

  it('persists sessions via writeJSON when upserting', () => {
    const session = {
      runId: 'run-2',
      procedureId: 'proc-1',
      messages: [],
    };
    const existingSessions = { existing: { runId: 'existing', procedureId: 'other', messages: [] } };
    mockedReadJSON.mockReturnValue(existingSessions);

    upsertSession(session);

    expect(existingSessions['run-2']).toEqual(session);
    expect(mockedWriteJSON).toHaveBeenCalledWith(storageKeys.sessions, existingSessions);
  });

  it('appends a message to a new session', () => {
    mockedReadJSON.mockReturnValueOnce({}).mockReturnValueOnce({});

    const message = {
      id: 'msg-1',
      role: 'assistant' as const,
      content: 'Hello',
      createdAt: '2023-01-01T00:00:00.000Z',
    };

    const session = appendMessage('run-3', message, 'proc-3');

    expect(session).toEqual({
      runId: 'run-3',
      procedureId: 'proc-3',
      messages: [message],
    });
    expect(mockedWriteJSON).toHaveBeenCalledWith(storageKeys.sessions, {
      'run-3': session,
    });
  });

  it('clears all sessions from storage', () => {
    clearSessions();

    expect(mockedStorageDelete).toHaveBeenCalledWith(storageKeys.sessions);
  });
});
