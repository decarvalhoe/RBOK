import { render, screen } from '@testing-library/react';

import { StatusBadge } from '../StatusBadge';

describe('StatusBadge', () => {
  it('renders the provided label with the default info styling', () => {
    render(<StatusBadge label="En attente" />);

    const badge = screen.getByRole('status', { name: /info status/i });
    expect(badge).toHaveTextContent('En attente');
    expect(badge.className).toContain('text-sky-800');
  });

  it('supports explicit variants for success and error states', () => {
    const { rerender } = render(<StatusBadge label="Succès" variant="success" />);

    let badge = screen.getByRole('status');
    expect(badge).toHaveAccessibleName('success status: Succès');
    expect(badge.className).toContain('text-emerald-800');

    rerender(<StatusBadge label="Erreur" variant="error" />);
    badge = screen.getByRole('status');
    expect(badge).toHaveAccessibleName('error status: Erreur');
    expect(badge.className).toContain('text-rose-800');
  });
});
