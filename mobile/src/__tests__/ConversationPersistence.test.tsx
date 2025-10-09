import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { QueryClient } from '@tanstack/react-query';
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import ConversationScreen from '../screens/ConversationScreen';
import { appendMessage, clearSessions, getSession } from '../storage/sessionStore';
import { cacheProcedureSteps } from '../storage/stepCache';
import { RootStackParamList } from '../navigation/types';
import { storage, storageKeys } from '../storage/mmkv';

describe('ConversationScreen persistence', () => {
  const Stack = createStackNavigator<RootStackParamList>();

  const createWrapper = () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    const persister = createSyncStoragePersister({
      storage: {
        getItem: (key: string) => storage.getString(key) ?? null,
        setItem: (key: string, value: string) => storage.set(key, value),
        removeItem: (key: string) => storage.delete(key),
      },
      key: storageKeys.reactQuery,
    });

    const Wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
      <PersistQueryClientProvider client={queryClient} persistOptions={{ persister, buster: 'test' }}>
        {children}
      </PersistQueryClientProvider>
    );

    return { Wrapper, queryClient };
  };

  const renderConversation = (Wrapper: React.ComponentType<{ children: React.ReactNode }>) => (
    <Wrapper>
      <NavigationContainer>
        <Stack.Navigator initialRouteName="Conversation">
          <Stack.Screen
            name="Conversation"
            component={ConversationScreen}
            initialParams={{ procedureId: 'proc-1', runId: 'run-1' }}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </Wrapper>
  );

  beforeEach(() => {
    clearSessions();
    storage.delete(storageKeys.reactQuery);
    cacheProcedureSteps('proc-1', ['Étape 1', 'Étape 2']);
    appendMessage('run-1', {
      id: 'existing-message',
      role: 'assistant',
      content: 'Bienvenue dans la session.',
      createdAt: new Date().toISOString(),
    }, 'proc-1');

    (global.fetch as jest.Mock).mockImplementation((url: string) => {
      if (url.endsWith('/procedures/proc-1')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          url,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                id: 'proc-1',
                name: 'Procédure persistante',
                description: 'Test',
                steps: [
                  { key: 'step-1', title: 'Étape 1', prompt: 'Faire A', slots: [] },
                  { key: 'step-2', title: 'Étape 2', prompt: 'Faire B', slots: [] },
                ],
              })
            ),
        });
      }

      if (url.endsWith('/runs/run-1')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          url,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                id: 'run-1',
                procedure_id: 'proc-1',
                user_id: 'user-1',
                state: 'started',
                created_at: new Date().toISOString(),
              })
            ),
        });
      }

      return Promise.resolve({
        ok: true,
        status: 200,
        url,
        text: () => Promise.resolve('{}'),
      });
    });
  });

  afterEach(() => {
    clearSessions();
    jest.clearAllTimers();
    jest.useRealTimers();
  });

  it('loads cached messages and persists new ones', async () => {
    jest.useFakeTimers();
    const { Wrapper, queryClient } = createWrapper();

    const { getByText, getByPlaceholderText } = render(renderConversation(Wrapper));

    expect(getByText('Bienvenue dans la session.')).toBeTruthy();

    const input = getByPlaceholderText('Votre message...');
    fireEvent.changeText(input, 'Nouvelle information');
    fireEvent.press(getByText('Envoyer'));

    await act(async () => {
      jest.runAllTimers();
    });

    await waitFor(() => {
      const session = getSession('run-1');
      expect(session?.messages.length).toBeGreaterThanOrEqual(3);
    });

    queryClient.clear();
  });
});
