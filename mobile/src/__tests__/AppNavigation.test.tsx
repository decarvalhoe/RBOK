import React from 'react';
import { act, fireEvent, render } from '@testing-library/react-native';
import App from '../App';

describe('App navigation', () => {
  it('navigates from home to procedure list and displays fetched procedures', async () => {
    (global.fetch as jest.Mock).mockImplementation((url: string) => {
      if (url.endsWith('/procedures')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          url,
          text: () =>
            Promise.resolve(
              JSON.stringify([
                { id: 'p1', name: 'Procédure test', description: 'Description', steps: [] },
              ])
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

    const { getByText, findByText } = render(<App />);

    await act(async () => {
      fireEvent.press(getByText('Explorer les procédures'));
    });

    expect(await findByText('Procédure test')).toBeTruthy();
  });
});
