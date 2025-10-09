import type React from 'react';

import '@testing-library/jest-native/extend-expect';
import 'react-native-gesture-handler/jestSetup';

jest.mock('react-native/Libraries/Animated/NativeAnimatedHelper');
jest.mock('react-native/Libraries/EventEmitter/NativeEventEmitter');


jest.mock('@react-navigation/native', () => {
  const actual = jest.requireActual('@react-navigation/native');
  return {
    ...actual,
    useNavigation: () => ({ navigate: jest.fn(), goBack: jest.fn() }),
    useRoute: () => ({ params: {} }),
  };
});

jest.mock('@react-navigation/stack', () => ({
  createStackNavigator: () => ({
    Navigator: ({ children }: { children: React.ReactNode }) => children,
    Screen: ({ children }: { children: React.ReactNode }) => children,
  }),
}));

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

jest.mock('react-native-keychain', () => ({
  setGenericPassword: jest.fn().mockResolvedValue(true),
  getGenericPassword: jest.fn().mockResolvedValue(null),
  resetGenericPassword: jest.fn().mockResolvedValue(true),
}));

jest.mock('react-native-webrtc', () => ({
  RTCPeerConnection: jest.fn().mockImplementation(() => ({
    createOffer: jest.fn().mockResolvedValue({ sdp: 'offer', type: 'offer' }),
    setLocalDescription: jest.fn().mockResolvedValue(undefined),
    close: jest.fn(),
    addTrack: jest.fn(),
    onicecandidate: null,
  })),
  mediaDevices: {
    getUserMedia: jest.fn().mockResolvedValue({}),
  },
}));

beforeEach(() => {
  (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    url: 'http://localhost/mock',
    text: () => Promise.resolve('[]'),
  });
});
