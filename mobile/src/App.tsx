import React from 'react';
import { AppState, AppStateStatus } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import {
  QueryCache,
  QueryClient,
  focusManager,
} from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import HomeScreen from './screens/HomeScreen';
import ProcedureListScreen from './screens/ProcedureListScreen';
import ProcedureDetailScreen from './screens/ProcedureDetailScreen';
import ConversationScreen from './screens/ConversationScreen';
import { RootStackParamList } from './navigation/types';
import { logError } from './analytics/logger';
import { storage, storageKeys } from './storage/mmkv';

const Stack = createStackNavigator<RootStackParamList>();

const queryCache = new QueryCache({
  onError: (error, query) => {
    logError({
      message: 'query_failed',
      context: { queryKey: query?.queryKey, error: (error as Error).message },
    });
  },
});

const queryClient = new QueryClient({
  queryCache,
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,
      cacheTime: 1000 * 60 * 60 * 24,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const CACHE_BUSTER = 'mobile-v1';

const persister = createSyncStoragePersister({
  storage: {
    getItem: (key: string) => storage.getString(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  },
  key: storageKeys.reactQuery,
});

const useAppStateFocus = () => {
  React.useEffect(() => {
    const onChange = (status: AppStateStatus) => {
      focusManager.setFocused(status === 'active');
    };
    const subscription = AppState.addEventListener('change', onChange);
    return () => subscription.remove();
  }, []);
};

export default function App() {
  useAppStateFocus();

  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{ persister, buster: CACHE_BUSTER }}
    >
      <NavigationContainer>
        <Stack.Navigator>
          <Stack.Screen
            name="Home"
            component={HomeScreen}
            options={{ headerShown: false }}
          />
          <Stack.Screen
            name="Procedures"
            component={ProcedureListScreen}
            options={{ title: 'Procédures' }}
          />
          <Stack.Screen
            name="ProcedureDetail"
            component={ProcedureDetailScreen}
            options={{ title: 'Détails de la procédure' }}
          />
          <Stack.Screen
            name="Conversation"
            component={ConversationScreen}
            options={{ title: 'Conversation' }}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </PersistQueryClientProvider>
  );
}
