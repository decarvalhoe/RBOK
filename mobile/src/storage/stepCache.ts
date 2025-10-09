import { readJSON, storageKeys, writeJSON } from './mmkv';

export type CachedProcedureSteps = Record<string, string[]>;

const getCache = (): CachedProcedureSteps =>
  readJSON<CachedProcedureSteps>(storageKeys.cachedSteps, {});

export const cacheProcedureSteps = (procedureId: string, steps: string[]) => {
  const cache = getCache();
  cache[procedureId] = steps;
  writeJSON(storageKeys.cachedSteps, cache);
};

export const getCachedProcedureSteps = (procedureId: string): string[] | undefined => {
  const cache = getCache();
  return cache[procedureId];
};
