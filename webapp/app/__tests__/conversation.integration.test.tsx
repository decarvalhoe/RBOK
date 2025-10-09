import userEvent from '@testing-library/user-event';
import { render, screen, waitFor } from '@testing-library/react';

import Home from '../page';
import { sendChatMessage } from '../../lib/api';

jest.mock('../../lib/api', () => ({
  sendChatMessage: jest.fn(),
}));

describe('Home conversation flow', () => {
  it('submits a message and renders the assistant response', async () => {
    const sendChatMessageSpy = sendChatMessage as jest.MockedFunction<typeof sendChatMessage>;
    sendChatMessageSpy.mockResolvedValue({ content: 'Réponse simulée' });

    const user = userEvent.setup();
    render(<Home />);

    const input = screen.getByLabelText(/message/i);
    await user.type(input, 'Bonjour');

    await user.click(screen.getByRole('button', { name: /envoyer/i }));

    await waitFor(() => {
      expect(screen.getByText('Réponse simulée')).toBeInTheDocument();
    });

    expect(sendChatMessageSpy).toHaveBeenCalledWith('Bonjour');
  });
});
