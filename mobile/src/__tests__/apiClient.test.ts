import { getProcedure, getProcedures, getRun, startProcedureRun } from '../api/client';
import { cacheProcedureSteps } from '../storage/stepCache';
import { logError, logEvent } from '../analytics/logger';

describe('api client', () => {
  beforeEach(() => {
    (logEvent as jest.Mock).mockClear();
    (logError as jest.Mock).mockClear();
    (cacheProcedureSteps as jest.Mock).mockClear();
    (global.fetch as jest.Mock).mockReset();
  });

  it('fetches procedures and logs success', async () => {
    const procedures = [
      { id: 'proc-1', name: 'Procédure', description: 'Test', steps: [] },
    ];

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      url: 'http://localhost:8000/procedures',
      text: () => Promise.resolve(JSON.stringify(procedures)),
    });

    const result = await getProcedures();

    expect(result).toEqual(procedures);
    expect(logEvent).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'request_succeeded', properties: { path: '/procedures' } })
    );
  });

  it('caches procedure steps on fetch', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      url: 'http://localhost:8000/procedures/proc-1',
      text: () =>
        Promise.resolve(
          JSON.stringify({
            id: 'proc-1',
            name: 'Procédure détaillée',
            description: 'Test',
            steps: [
              { key: 's1', title: 'Étape A', prompt: 'Faire A', slots: [] },
              { key: 's2', title: 'Étape B', prompt: 'Faire B', slots: [] },
            ],
          })
        ),
    });

    const result = await getProcedure('proc-1');

    expect(result.steps).toHaveLength(2);
    expect(cacheProcedureSteps).toHaveBeenCalledWith('proc-1', ['Étape A', 'Étape B']);
  });

  it('throws with detailed error when response not ok', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 500,
      url: 'http://localhost:8000/procedures/proc-1',
      text: () => Promise.resolve(''),
    });

    await expect(getProcedure('proc-1')).rejects.toThrow('HTTP 500');
    expect(logError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'request_failed', context: expect.objectContaining({ status: 500 }) })
    );
    expect(logError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'network_error', context: expect.objectContaining({ path: '/procedures/proc-1' }) })
    );
  });

  it('logs network errors and rethrows', async () => {
    (global.fetch as jest.Mock).mockRejectedValue(new Error('disconnected'));

    await expect(getProcedures()).rejects.toThrow('disconnected');
    expect(logError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'network_error', context: expect.objectContaining({ path: '/procedures' }) })
    );
  });

  it('starts a procedure run with optional user id', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 201,
      url: 'http://localhost:8000/runs?procedure_id=proc-1&user_id=user-1',
      text: () =>
        Promise.resolve(
          JSON.stringify({ id: 'run-1', procedure_id: 'proc-1', user_id: 'user-1', state: 'started' })
        ),
    });

    const run = await startProcedureRun('proc-1', 'user-1');

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/runs?procedure_id=proc-1&user_id=user-1',
      expect.objectContaining({ method: 'POST' })
    );
    expect(run.id).toBe('run-1');
  });

  it('logs failures when starting a procedure run fails', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 503,
      url: 'http://localhost:8000/runs?procedure_id=proc-1',
      text: () => Promise.resolve(''),
    });

    await expect(startProcedureRun('proc-1')).rejects.toThrow('HTTP 503');

    expect(logError).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'request_failed',
        context: expect.objectContaining({ status: 503, url: 'http://localhost:8000/runs?procedure_id=proc-1' }),
      })
    );
    expect(logError).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'network_error',
        context: expect.objectContaining({ path: '/runs?procedure_id=proc-1' }),
      })
    );
  });

  it('retrieves procedure runs', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      url: 'http://localhost:8000/runs/run-1',
      text: () =>
        Promise.resolve(
          JSON.stringify({ id: 'run-1', procedure_id: 'proc-1', user_id: 'user-1', state: 'started' })
        ),
    });

    const run = await getRun('run-1');

    expect(run).toEqual(
      expect.objectContaining({ id: 'run-1', procedure_id: 'proc-1', user_id: 'user-1', state: 'started' })
    );
  });
});

jest.mock('../analytics/logger', () => ({
  logEvent: jest.fn(),
  logError: jest.fn(),
}));

jest.mock('../storage/stepCache', () => ({
  cacheProcedureSteps: jest.fn(),
}));
