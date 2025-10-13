import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ProcedureDetailScreen from '../screens/ProcedureDetailScreen';
import { useNavigation, useRoute } from '@react-navigation/native';
import { storage, storageKeys } from '../storage/mmkv';
import { clearSessions } from '../storage/sessionStore';

jest.mock('@react-navigation/native', () => {
  const actual = jest.requireActual('@react-navigation/native');
  return {
    ...actual,
    useNavigation: jest.fn(),
    useRoute: jest.fn(),
  };
});

const useNavigationMock = useNavigation as jest.Mock;
const useRouteMock = useRoute as jest.Mock;

const createClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

const renderWithClient = (client: QueryClient) =>
  render(
    <QueryClientProvider client={client}>
      <ProcedureDetailScreen />
    </QueryClientProvider>
  );

describe('ProcedureDetailScreen', () => {
  const navigateMock = jest.fn();
  let client: QueryClient;

  beforeEach(() => {
    client = createClient();
    useRouteMock.mockReturnValue({ params: { procedureId: 'proc-1' } });
    useNavigationMock.mockReturnValue({ navigate: navigateMock });
    navigateMock.mockClear();
    (global.fetch as jest.Mock).mockReset();
    storage.delete(storageKeys.cachedSteps);
    clearSessions();
  });

  afterEach(() => {
    client.clear();
  });

  it('renders loading state while fetching', () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      url: 'http://localhost:8000/procedures/proc-1',
      text: () => Promise.resolve('{}'),
    });

    const { getByText } = renderWithClient(client);

    expect(getByText('Chargement de la procédure')).toBeTruthy();
  });

  it('renders error state when fetch fails and retries on press', async () => {
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        url: 'http://localhost:8000/procedures/proc-1',
        text: () => Promise.resolve(''),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        url: 'http://localhost:8000/procedures/proc-1',
        text: () =>
          Promise.resolve(
            JSON.stringify({
              id: 'proc-1',
              name: 'Procédure test',
              description: 'Description',
              steps: [],
            })
          ),
      });

    const { findByText, getByText } = renderWithClient(client);

    expect(await findByText('Impossible de charger cette procédure.')).toBeTruthy();

    await act(async () => {
      fireEvent.press(getByText('Réessayer'));
    });

    await waitFor(() => expect(getByText('Procédure test')).toBeTruthy());
  });

  it('starts a run and navigates to conversation on success', async () => {
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        url: 'http://localhost:8000/procedures/proc-1',
        text: () =>
          Promise.resolve(
            JSON.stringify({
              id: 'proc-1',
              name: 'Procédure complète',
              description: 'Description',
              steps: [{ key: 's1', title: 'Étape A', prompt: 'Faire A', slots: [] }],
            })
          ),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        url: 'http://localhost:8000/runs?procedure_id=proc-1',
        text: () =>
          Promise.resolve(
            JSON.stringify({ id: 'run-123', procedure_id: 'proc-1', user_id: null, state: 'started' })
          ),
      });

    const { findByText, getByText } = renderWithClient(client);

    expect(await findByText('Procédure complète')).toBeTruthy();

    await act(async () => {
      fireEvent.press(getByText('Démarrer une conversation'));
    });

    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('Conversation', {
        procedureId: 'proc-1',
        runId: 'run-123',
      })
    );
  });

  it('handles run creation errors gracefully', async () => {
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        url: 'http://localhost:8000/procedures/proc-1',
        text: () =>
          Promise.resolve(
            JSON.stringify({
              id: 'proc-1',
              name: 'Procédure complète',
              description: 'Description',
              steps: [{ key: 's1', title: 'Étape A', prompt: 'Faire A', slots: [] }],
            })
          ),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        url: 'http://localhost:8000/runs?procedure_id=proc-1',
        text: () => Promise.resolve(''),
      });

    const { findByText, getByText } = renderWithClient(client);

    expect(await findByText('Procédure complète')).toBeTruthy();

    await act(async () => {
      fireEvent.press(getByText('Démarrer une conversation'));
    });

    await waitFor(() => expect(navigateMock).not.toHaveBeenCalled());
  });
});
