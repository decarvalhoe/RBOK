import { cacheProcedureSteps, getCachedProcedureSteps } from '../stepCache';
import { readJSON, storageKeys, writeJSON } from '../mmkv';

jest.mock('../mmkv', () => ({
  readJSON: jest.fn(),
  writeJSON: jest.fn(),
  storageKeys: { sessions: 'sessions', cachedSteps: 'cached-steps' },
}));

const mockedReadJSON = readJSON as jest.Mock;
const mockedWriteJSON = writeJSON as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
});

afterEach(() => {
  jest.clearAllMocks();
});

afterAll(() => {
  jest.resetModules();
});

describe('stepCache', () => {
  it('persists cached steps through writeJSON', () => {
    const existingCache = { other: ['Alpha'] };
    mockedReadJSON.mockReturnValue(existingCache);

    cacheProcedureSteps('proc-1', ['First', 'Second']);

    expect(existingCache['proc-1']).toEqual(['First', 'Second']);
    expect(mockedWriteJSON).toHaveBeenCalledWith(storageKeys.cachedSteps, existingCache);
  });

  it('hydrates cached steps from storage', () => {
    mockedReadJSON.mockReturnValueOnce({ 'proc-2': ['Stored'] });

    expect(getCachedProcedureSteps('proc-2')).toEqual(['Stored']);
    expect(mockedReadJSON).toHaveBeenCalledWith(storageKeys.cachedSteps, {});
  });
});
