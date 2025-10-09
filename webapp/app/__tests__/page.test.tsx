import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Home from '../page';
import { sendChatMessage } from '../../lib/api';
import { MESSAGE_MAX_LENGTH } from '../../lib/messageConstraints';

jest.mock('../../lib/api', () => ({
  sendChatMessage: jest.fn(),
}));

const mockedSendChatMessage = sendChatMessage as jest.MockedFunction<typeof sendChatMessage>;

describe('Home page conversation flow', () => {
  beforeEach(() => {
    mockedSendChatMessage.mockReset();
  });

  it('sends the message and renders the assistant response on success', async () => {
    let resolvePromise: (value: { role: string; content: string }) => void;
    const pendingResponse = new Promise<{ role: string; content: string }>((resolve) => {
      resolvePromise = resolve;
    });

    mockedSendChatMessage.mockReturnValueOnce(pendingResponse);

    render(<Home />);

    const input = screen.getByLabelText(/message/i);
    await userEvent.type(input, 'Salut');

    await userEvent.click(screen.getByRole('button', { name: /envoyer/i }));

    expect(mockedSendChatMessage).toHaveBeenCalledWith('Salut');

    expect(screen.getByText('Assistant est en train de répondre...')).toBeInTheDocument();

    await act(async () => {
      resolvePromise({ role: 'assistant', content: 'Bonjour! Comment puis-je vous aider ?' });
      await pendingResponse;
    });

    await waitFor(() => {
      expect(screen.queryByText('Assistant est en train de répondre...')).not.toBeInTheDocument();
    });

    expect(screen.getByText('Bonjour! Comment puis-je vous aider ?')).toBeInTheDocument();
  });

  it('displays an error message when the backend returns an error', async () => {
    mockedSendChatMessage.mockRejectedValueOnce(new Error('Incident serveur'));

    render(<Home />);

    const input = screen.getByLabelText(/message/i);
    await userEvent.type(input, 'Aide moi');

    await userEvent.click(screen.getByRole('button', { name: /envoyer/i }));

    expect(mockedSendChatMessage).toHaveBeenCalledWith('Aide moi');

    await waitFor(() => {
      expect(screen.getByText(/Erreur serveur: Incident serveur/)).toBeInTheDocument();
    });

    expect(screen.getByText('Aide moi')).toBeInTheDocument();
  });

  it('prevents submission of blank messages and shows validation feedback', async () => {
    render(<Home />);

    const input = screen.getByLabelText(/message/i);
    await userEvent.type(input, '   ');

    await userEvent.click(screen.getByRole('button', { name: /envoyer/i }));

    expect(mockedSendChatMessage).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Le message doit contenir au moins');
  });

  it('shows an error when the message exceeds the maximum length', async () => {
    render(<Home />);

    const input = screen.getByLabelText(/message/i);
    const overSizedMessage = 'a'.repeat(MESSAGE_MAX_LENGTH + 1);
    await userEvent.type(input, overSizedMessage);

    await userEvent.click(screen.getByRole('button', { name: /envoyer/i }));

    expect(mockedSendChatMessage).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('ne peut pas dépasser');
  });
});
