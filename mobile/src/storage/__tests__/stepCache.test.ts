import { storage, storageKeys } from '../mmkv';
import { cacheProcedureSteps, getCachedProcedureSteps } from '../stepCache';

describe('step cache helpers', () => {
  beforeEach(() => {
    storage.delete(storageKeys.cachedSteps);
  });

  it('returns undefined when no cache exists', () => {
    expect(getCachedProcedureSteps('missing')).toBeUndefined();
  });

  it('stores and retrieves procedure steps', () => {
    cacheProcedureSteps('proc-1', ['Step 1', 'Step 2']);

    expect(getCachedProcedureSteps('proc-1')).toEqual(['Step 1', 'Step 2']);
  });

  it('merges steps across procedures', () => {
    cacheProcedureSteps('proc-1', ['Step 1']);
    cacheProcedureSteps('proc-2', ['Step A']);

    expect(getCachedProcedureSteps('proc-1')).toEqual(['Step 1']);
    expect(getCachedProcedureSteps('proc-2')).toEqual(['Step A']);
  });
});
