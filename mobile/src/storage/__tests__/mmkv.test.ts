import { readJSON, removeKey, storage, storageKeys, writeJSON } from '../mmkv';

describe('mmkv helpers', () => {
  beforeEach(() => {
    storage.delete(storageKeys.sessions);
    storage.delete(storageKeys.cachedSteps);
    storage.delete(storageKeys.reactQuery);
  });

  it('returns fallback when key missing', () => {
    const fallback = { foo: 'bar' };
    const result = readJSON('unknown', fallback);
    expect(result).toEqual(fallback);
  });

  it('returns parsed json when stored', () => {
    writeJSON(storageKeys.sessions, { answer: 42 });
    const result = readJSON(storageKeys.sessions, {});
    expect(result).toEqual({ answer: 42 });
  });

  it('returns fallback when parsing fails', () => {
    storage.set(storageKeys.sessions, 'not-json');
    const result = readJSON(storageKeys.sessions, { ok: false });
    expect(result).toEqual({ ok: false });
  });

  it('removes keys from storage', () => {
    writeJSON(storageKeys.sessions, { answer: 42 });
    removeKey(storageKeys.sessions);
    const result = readJSON(storageKeys.sessions, null);
    expect(result).toBeNull();
  });
});
