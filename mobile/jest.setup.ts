import '@testing-library/jest-native/extend-expect';
import 'react-native-gesture-handler/jestSetup';

jest.mock('react-native/Libraries/Animated/NativeAnimatedHelper');

jest.mock('react-native-mmkv', () => {
  class MockMMKV {
    storage = new Map<string, string>();
    set(key: string, value: string) {
      this.storage.set(key, value);
    }
    getString(key: string) {
      return this.storage.has(key) ? this.storage.get(key)! : null;
    }
    delete(key: string) {
      this.storage.delete(key);
    }
  }
  return { MMKV: MockMMKV };
});

beforeEach(() => {
  (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    url: 'http://localhost/mock',
    text: () => Promise.resolve('[]'),
  });
});
