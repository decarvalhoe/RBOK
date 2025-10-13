import type { Procedure } from '../types';
import { getProcedure, getProcedures, getRun, startProcedureRun } from '../client';
import { logEvent, logError } from '../../analytics/logger';
import { cacheProcedureSteps } from '../../storage/stepCache';

type MockResponse = {
  ok: boolean;
  status: number;
  url: string;
  text: () => Promise<string>;
};

jest.mock('../../analytics/logger', () => ({
  logEvent: jest.fn(),
  logError: jest.fn(),
}));

jest.mock('../../storage/stepCache', () => ({
  cacheProcedureSteps: jest.fn(),
}));

describe('api client', () => {
  const originalFetch = global.fetch;
  const fetchMock = jest.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    global.fetch = fetchMock;
  });

  afterEach(() => {
    jest.clearAllMocks();
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error assigning undefined is acceptable for cleanup
      global.fetch = undefined;
    }
  });

  const createResponse = (overrides: Partial<MockResponse> = {}): MockResponse => ({
    ok: true,
    status: 200,
    url: 'http://localhost:8000/test',
    text: async () => '"ok"',
    ...overrides,
  });

  it('fetches procedures successfully and logs the success event', async () => {
    const procedures = [{ id: '1', name: 'Test', description: '', steps: [] }] as Procedure[];
    const response = createResponse({ text: async () => JSON.stringify(procedures) });
    fetchMock.mockResolvedValue(response);

    await expect(getProcedures()).resolves.toEqual(procedures);

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/procedures', {
      headers: { 'Content-Type': 'application/json' },
    });
    expect(logEvent).toHaveBeenCalledWith({
      name: 'request_succeeded',
      properties: { path: '/procedures' },
    });
    expect(logError).not.toHaveBeenCalled();
  });

  it('caches procedure steps when fetching a procedure', async () => {
    const procedure: Procedure = {
      id: 'proc-1',
      name: 'Proc',
      description: 'Desc',
      steps: [
        { key: 'step-1', title: 'First', prompt: '', slots: [] },
        { key: 'step-2', title: 'Second', prompt: '', slots: [] },
      ],
    };
    const response = createResponse({ text: async () => JSON.stringify(procedure) });
    fetchMock.mockResolvedValue(response);

    await expect(getProcedure('proc-1')).resolves.toEqual(procedure);

    expect(cacheProcedureSteps).toHaveBeenCalledWith('proc-1', ['First', 'Second']);
  });

  it('throws and logs errors when the response is not ok', async () => {
    const response = createResponse({
      ok: false,
      status: 404,
      url: 'http://localhost:8000/runs/run-404',
    });
    fetchMock.mockResolvedValue(response);

    await expect(getRun('run-404')).rejects.toThrow('HTTP 404');

    expect(logError).toHaveBeenNthCalledWith(1, {
      message: 'request_failed',
      context: { url: 'http://localhost:8000/runs/run-404', status: 404 },
    });
    expect(logError).toHaveBeenNthCalledWith(2, {
      message: 'network_error',
      context: {
        path: '/runs/run-404',
        error: expect.any(Error),
      },
    });
  });

  it('logs network errors when fetch rejects', async () => {
    const error = new Error('Network down');
    fetchMock.mockRejectedValue(error);

    await expect(getProcedures()).rejects.toThrow('Network down');

    expect(logError).toHaveBeenCalledWith({
      message: 'network_error',
      context: { path: '/procedures', error },
    });
  });

  it('builds the correct URL when starting a procedure run', async () => {
    const runResponse = { id: 'run-1' };
    const response = createResponse({ text: async () => JSON.stringify(runResponse) });
    fetchMock.mockResolvedValue(response);

    await startProcedureRun('proc-42', 'user-99');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/runs?procedure_id=proc-42&user_id=user-99',
      expect.objectContaining({ method: 'POST' })
    );
  });
});
