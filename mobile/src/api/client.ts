import { logError, logEvent } from '../analytics/logger';
import { cacheProcedureSteps } from '../storage/stepCache';
import { Procedure, ProcedureRun } from './types';

const API_BASE_URL = process.env.API_BASE_URL ?? 'http://localhost:8000';

type FetchOptions = RequestInit & { raw?: boolean };

const handleResponse = async <T>(response: Response): Promise<T> => {
  if (!response.ok) {
    const message = `HTTP ${response.status}`;
    const context = { url: response.url };
    logError({ message: 'request_failed', context: { ...context, status: response.status } });
    throw new Error(message);
  }

  const text = await response.text();
  return text.length ? (JSON.parse(text) as T) : ({} as T);
};

const fetchJSON = async <T>(path: string, options?: FetchOptions): Promise<T> => {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(options?.headers ?? {}),
      },
      ...options,
    });

    if (options?.raw) {
      return (response as unknown) as T;
    }

    const data = await handleResponse<T>(response);
    logEvent({ name: 'request_succeeded', properties: { path } });
    return data;
  } catch (error) {
    logError({ message: 'network_error', context: { path, error } });
    throw error;
  }
};

export const getProcedures = () => fetchJSON<Procedure[]>('/procedures');

export const getProcedure = async (procedureId: string) => {
  const procedure = await fetchJSON<Procedure>(`/procedures/${procedureId}`);
  cacheProcedureSteps(
    procedureId,
    procedure.steps.map((step) => step.title)
  );
  return procedure;
};

export const startProcedureRun = (procedureId: string, userId?: string) => {
  const searchParams = new URLSearchParams({ procedure_id: procedureId });
  if (userId) {
    searchParams.set('user_id', userId);
  }

  return fetchJSON<ProcedureRun>(`/runs?${searchParams.toString()}`, {
    method: 'POST',
  });
};

export const getRun = (runId: string) => fetchJSON<ProcedureRun>(`/runs/${runId}`);
