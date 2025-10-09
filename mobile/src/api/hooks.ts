import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { logEvent } from '../analytics/logger';
import { appendMessage } from '../storage/sessionStore';
import { getCachedProcedureSteps } from '../storage/stepCache';
import { getProcedure, getProcedures, getRun, startProcedureRun } from './client';
import { Procedure, ProcedureRun } from './types';

export const queryKeys = {
  procedures: ['procedures'] as const,
  procedure: (procedureId: string) => ['procedure', procedureId] as const,
  run: (runId: string) => ['run', runId] as const,
};

export const useProcedures = () =>
  useQuery({
    queryKey: queryKeys.procedures,
    queryFn: getProcedures,
  });

export const useProcedure = (procedureId: string) =>
  useQuery({
    queryKey: queryKeys.procedure(procedureId),
    queryFn: () => getProcedure(procedureId),
    placeholderData: () => {
      const cachedTitles = getCachedProcedureSteps(procedureId);
      if (!cachedTitles) {
        return undefined;
      }
      const placeholder: Procedure = {
        id: procedureId,
        name: 'Procédure hors-ligne',
        description: 'Cette procédure provient du cache local.',
        steps: cachedTitles.map((title, index) => ({
          key: `${procedureId}-cached-${index}`,
          title,
          prompt: '',
          slots: [],
        })),
      };
      return placeholder;
    },
  });

export const useRun = (runId: string) =>
  useQuery({
    queryKey: queryKeys.run(runId),
    queryFn: () => getRun(runId),
    enabled: Boolean(runId),
  });

export const useStartProcedureRun = (procedureId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId }: { userId?: string } = {}) =>
      startProcedureRun(procedureId, userId),
    onSuccess: (run: ProcedureRun) => {
      queryClient.setQueryData(queryKeys.run(run.id), run);
      appendMessage(run.id, {
        id: `${run.id}-init`,
        role: 'assistant',
        content: 'Session initialisée.',
        createdAt: new Date().toISOString(),
      }, procedureId);
      logEvent({ name: 'procedure_run_started', properties: { procedureId, runId: run.id } });
    },
  });
};
