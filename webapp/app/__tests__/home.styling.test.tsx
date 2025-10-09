import { render, screen } from '@testing-library/react'
import Home from '../page'

describe('Home page styling', () => {
  it('renders the chat container with Tailwind utility classes', () => {
    render(<Home />)

    const chatSection = screen.getByRole('region', { name: /historique de conversation/i })
    expect(chatSection).toHaveClass('chat-container')
    expect(chatSection).toHaveClass('bg-white')
    expect(chatSection).toHaveClass('ring-1')
  })

  it('renders the send button with the primary color classes', () => {
    render(<Home />)

    const sendButton = screen.getByRole('button', { name: /envoyer/i })
    expect(sendButton).toHaveClass('bg-blue-600')
    expect(sendButton).toHaveClass('hover:bg-blue-700')
  })
})
