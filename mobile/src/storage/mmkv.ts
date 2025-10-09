import { MMKV } from 'react-native-mmkv';

export const storage = new MMKV({ id: 'realisons-storage' });

export const storageKeys = {
  sessions: 'sessions',
  cachedSteps: 'cached-steps',
  reactQuery: 'react-query-cache',
};

export const readJSON = <T>(key: string, fallback: T): T => {
  try {
    const value = storage.getString(key);
    return value ? (JSON.parse(value) as T) : fallback;
  } catch (error) {
    return fallback;
  }
};

export const writeJSON = (key: string, value: unknown) => {
  storage.set(key, JSON.stringify(value));
};

export const removeKey = (key: string) => {
  storage.delete(key);
};
