import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import * as NavigationNative from '@react-navigation/native';
import ConversationScreen from '../screens/ConversationScreen';
import * as SessionStore from '../storage/sessionStore';
import { cacheProcedureSteps } from '../storage/stepCache';
import * as Hooks from '../api/hooks';

const createProcedureResult = (overrides: Partial<ReturnType<typeof Hooks.useProcedure>>) => ({
  data: undefined,
  isLoading: false,
  error: undefined,
  refetch: jest.fn(),
  isFetching: false,
  ...overrides,
});

describe('ConversationScreen', () => {
  const useRouteSpy = jest.spyOn(NavigationNative, 'useRoute');
  const useProcedureSpy = jest.spyOn(Hooks, 'useProcedure');
  const useRunSpy = jest.spyOn(Hooks, 'useRun');

  beforeAll(() => {
    (global as unknown as { requestAnimationFrame?: (cb: any) => number }).requestAnimationFrame = ((cb: any) => {
      const id = setTimeout(() => cb(0), 0);
      return id as unknown as number;
    }) as (cb: any) => number;
  });

  beforeEach(() => {
    jest.useFakeTimers();
    SessionStore.clearSessions();
    cacheProcedureSteps('proc-1', ['Étape 1']);
    useRouteSpy.mockReturnValue({ params: { procedureId: 'proc-1', runId: 'run-1' } } as never);
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
    useRouteSpy.mockReset();
    useProcedureSpy.mockReset();
    useRunSpy.mockReset();
  });

  afterAll(() => {
    useRouteSpy.mockRestore();
    useProcedureSpy.mockRestore();
    useRunSpy.mockRestore();
  });

  it('renders loading state while procedure is loading and no cached session', () => {
    useProcedureSpy.mockReturnValue(createProcedureResult({ isLoading: true }));
    useRunSpy.mockReturnValue({ data: undefined } as ReturnType<typeof Hooks.useRun>);

    const { getByText } = render(<ConversationScreen />);

    expect(getByText('Chargement de la conversation')).toBeTruthy();
  });

  it('renders error state when procedure fails to load', async () => {
    const refetch = jest.fn();
    useProcedureSpy.mockReturnValue(
      createProcedureResult({ error: new Error('failed'), refetch })
    );
    useRunSpy.mockReturnValue({ data: undefined } as ReturnType<typeof Hooks.useRun>);

    const { getByText, findByText } = render(<ConversationScreen />);

    expect(await findByText('Impossible de récupérer les détails de la procédure.')).toBeTruthy();

    fireEvent.press(getByText('Réessayer'));

    expect(refetch).toHaveBeenCalled();
  });

  it('appends user and assistant messages during conversation flow', async () => {
    useProcedureSpy.mockReturnValue(
      createProcedureResult({
        data: {
          id: 'proc-1',
          name: 'Procédure active',
          description: 'Description',
          steps: [
            { key: 's1', title: 'Étape 1', prompt: 'Faire A', slots: [] },
            { key: 's2', title: 'Étape 2', prompt: 'Faire B', slots: [] },
          ],
        },
      } as ReturnType<typeof Hooks.useProcedure>)
    );
    useRunSpy.mockReturnValue({ data: { id: 'run-1' } } as ReturnType<typeof Hooks.useRun>);

    const { getByPlaceholderText, getByText, findByText } = render(<ConversationScreen />);

    expect(await findByText('Procédure active')).toBeTruthy();

    const input = getByPlaceholderText('Votre message...');
    await act(async () => {
      fireEvent.changeText(input, 'Bonjour');
    });

    await act(async () => {
      fireEvent.press(getByText('Envoyer'));
    });

    expect(getByText('...')).toBeTruthy();

    act(() => {
      jest.runAllTimers();
    });

    await waitFor(() => expect(getByText('Bonjour')).toBeTruthy());
  });

  it('restores cached sessions when available', async () => {
    const existingMessage: SessionStore.ConversationMessage = {
      id: 'run-1-assistant-1',
      role: 'assistant',
      content: 'Message précédant',
      createdAt: new Date('2024-01-01T10:00:00.000Z').toISOString(),
    };
    const session: SessionStore.ConversationSession = {
      runId: 'run-1',
      procedureId: 'proc-1',
      messages: [existingMessage],
    };
    const getSessionSpy = jest.spyOn(SessionStore, 'getSession').mockReturnValue(session);

    try {
      useProcedureSpy.mockReturnValue(createProcedureResult({ isLoading: true }));
      useRunSpy.mockReturnValue({ data: { id: 'run-1' } } as ReturnType<typeof Hooks.useRun>);

      const { findByText } = render(<ConversationScreen />);

      await expect(findByText('Message précédant')).resolves.toBeTruthy();
      expect(getSessionSpy).toHaveBeenCalled();
    } finally {
      getSessionSpy.mockRestore();
    }
  });

  it('ignores attempts to send blank messages', async () => {
    const appendSpy = jest.spyOn(SessionStore, 'appendMessage');

    try {
      useProcedureSpy.mockReturnValue(
        createProcedureResult({
          data: {
            id: 'proc-1',
            name: 'Procédure active',
            description: 'Description',
            steps: [],
          },
        } as ReturnType<typeof Hooks.useProcedure>)
      );
      useRunSpy.mockReturnValue({ data: { id: 'run-1' } } as ReturnType<typeof Hooks.useRun>);

      const { getByPlaceholderText, getByTestId } = render(<ConversationScreen />);

      await act(async () => {
        fireEvent.changeText(getByPlaceholderText('Votre message...'), '   ');
      });

      const sendButton = getByTestId('send-button');
      expect(sendButton).toBeDisabled();

      await act(async () => {
        fireEvent.press(sendButton);
      });

      expect(appendSpy).not.toHaveBeenCalled();
    } finally {
      appendSpy.mockRestore();
    }
  });
});
