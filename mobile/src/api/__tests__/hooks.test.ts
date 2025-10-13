import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { logEvent } from '../../analytics/logger';
import { appendMessage } from '../../storage/sessionStore';
import { getCachedProcedureSteps } from '../../storage/stepCache';
import {
  getProcedure,
  getProcedures,
  getRun,
  startProcedureRun,
} from '../client';
import { queryKeys, useProcedure, useProcedures, useRun, useStartProcedureRun } from '../hooks';

jest.mock('@tanstack/react-query', () => ({
  useQuery: jest.fn(),
  useMutation: jest.fn(),
  useQueryClient: jest.fn(),
}));

jest.mock('../client', () => ({
  getProcedure: jest.fn(),
  getProcedures: jest.fn(),
  getRun: jest.fn(),
  startProcedureRun: jest.fn(),
}));

jest.mock('../../storage/sessionStore', () => ({
  appendMessage: jest.fn(),
}));

jest.mock('../../storage/stepCache', () => ({
  getCachedProcedureSteps: jest.fn(),
}));

jest.mock('../../analytics/logger', () => ({
  logEvent: jest.fn(),
}));

const mockedUseQuery = useQuery as jest.Mock;
const mockedUseMutation = useMutation as jest.Mock;
const mockedUseQueryClient = useQueryClient as jest.Mock;

const mockedGetProcedures = getProcedures as jest.Mock;
const mockedGetProcedure = getProcedure as jest.Mock;
const mockedGetRun = getRun as jest.Mock;
const mockedStartProcedureRun = startProcedureRun as jest.Mock;
const mockedAppendMessage = appendMessage as jest.Mock;
const mockedGetCachedProcedureSteps = getCachedProcedureSteps as jest.Mock;
const mockedLogEvent = logEvent as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  mockedUseQuery.mockReturnValue('query-result');
  mockedUseMutation.mockReturnValue({ mutateAsync: jest.fn() });
  mockedUseQueryClient.mockReturnValue({ setQueryData: jest.fn() });
  mockedGetProcedure.mockResolvedValue({});
  mockedGetRun.mockResolvedValue({});
  mockedGetProcedures.mockResolvedValue([]);
});

afterEach(() => {
  jest.clearAllMocks();
});

afterAll(() => {
  jest.resetModules();
});

describe('React Query hooks', () => {
  it('uses the procedures query configuration', () => {
    const result = useProcedures();

    expect(result).toBe('query-result');
    expect(mockedUseQuery).toHaveBeenCalledWith({
      queryKey: queryKeys.procedures,
      queryFn: mockedGetProcedures,
    });
  });

  it('hydrates placeholder data from cached procedure steps', async () => {
    mockedGetCachedProcedureSteps.mockReturnValue(['First', 'Second']);

    mockedUseQuery.mockImplementation((options) => {
      const placeholder = options.placeholderData?.();
      expect(placeholder).toMatchObject({
        id: 'proc-1',
        steps: [
          { title: 'First' },
          { title: 'Second' },
        ],
      });
      return 'procedure-result';
    });

    const result = useProcedure('proc-1');

    expect(result).toBe('procedure-result');
    expect(mockedUseQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: queryKeys.procedure('proc-1'),
        queryFn: expect.any(Function),
      })
    );

    const options = mockedUseQuery.mock.calls[0][0];
    await options.queryFn();
    expect(mockedGetProcedure).toHaveBeenCalledWith('proc-1');
  });

  it('disables the run query when no id is provided', async () => {
    mockedUseQuery.mockReturnValue('run-result');

    const result = useRun('');

    expect(result).toBe('run-result');
    expect(mockedUseQuery).toHaveBeenCalledWith({
      queryKey: queryKeys.run(''),
      queryFn: expect.any(Function),
      enabled: false,
    });

    const options = mockedUseQuery.mock.calls[0][0];
    await options.queryFn();
    expect(mockedGetRun).toHaveBeenCalledWith('');
  });

  it('provides mutation handlers that seed the cache and store the session', () => {
    const setQueryData = jest.fn();
    mockedUseQueryClient.mockReturnValue({ setQueryData });

    let capturedConfig: any;
    mockedUseMutation.mockImplementation((config) => {
      capturedConfig = config;
      return { mutateAsync: jest.fn() };
    });

    const hookResult = useStartProcedureRun('proc-99');

    expect(hookResult).toEqual({ mutateAsync: expect.any(Function) });
    expect(mockedUseMutation).toHaveBeenCalled();

    capturedConfig.mutationFn({ userId: 'user-2' });
    expect(mockedStartProcedureRun).toHaveBeenCalledWith('proc-99', 'user-2');

    const run = {
      id: 'run-123',
      procedureId: 'proc-99',
    };
    capturedConfig.onSuccess(run);

    expect(setQueryData).toHaveBeenCalledWith(queryKeys.run('run-123'), run);
    expect(mockedAppendMessage).toHaveBeenCalledWith(
      'run-123',
      expect.objectContaining({
        id: 'run-123-init',
        role: 'assistant',
      }),
      'proc-99'
    );
    expect(mockedLogEvent).toHaveBeenCalledWith({
      name: 'procedure_run_started',
      properties: { procedureId: 'proc-99', runId: 'run-123' },
    });
  });
});
