'use client';

import { useCallback, useMemo, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { sendChatMessage } from '../lib/api';

type MessageStatus = 'pending' | 'success' | 'error';

type ConversationMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  status: MessageStatus;
};

const PENDING_TEXT = "Assistant est en train de répondre...";

const getErrorMessage = (error: unknown): string => {
  if (typeof error === 'string') {
    return error;
  }

  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string; message?: string }; status?: number } }).response;
    const detail = response?.data?.detail ?? response?.data?.message;
    if (detail) {
      return `Erreur serveur: ${detail}`;
    }
    if (response?.status) {
      return `Erreur serveur: code ${response.status}`;
    }
  }

  if (error instanceof Error) {
    return `Erreur serveur: ${error.message}`;
  }

  return 'Une erreur inconnue est survenue.';
};

export default function Home() {
  const [message, setMessage] = useState('');
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const isSendDisabled = useMemo(() => isLoading || !message.trim(), [isLoading, message]);

  const handleSendMessage = useCallback(async () => {
    if (!message.trim() || isLoading) return;

    const trimmedMessage = message.trim();
    const userMessage: ConversationMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmedMessage,
      status: 'success',
    };

    const pendingMessage: ConversationMessage = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: PENDING_TEXT,
      status: 'pending',
    };

    setConversation((prev) => [...prev, userMessage, pendingMessage]);
    setMessage('');
    setIsLoading(true);

    try {
      const response = await sendChatMessage(trimmedMessage);
      const assistantContent = response?.content?.trim()
        ? response.content
        : "L'assistant n'a renvoyé aucun contenu.";

      setConversation((prev) =>
        prev.map((msg) =>
          msg.id === pendingMessage.id
            ? { ...msg, content: assistantContent, status: 'success' }
            : msg,
        ),
      );
    } catch (error) {
      const errorMessage = getErrorMessage(error);
      setConversation((prev) =>
        prev.map((msg) =>
          msg.id === pendingMessage.id
            ? { ...msg, content: errorMessage, status: 'error' }
            : msg,
        ),
      );
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, message]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        handleSendMessage();
      }
    },
    [handleSendMessage],
  );

  return (
    <main className="container mx-auto p-4">
      <h1 className="text-3xl font-bold mb-6">Assistant Procédural "Réalisons" v0.1</h1>

      <div className="chat-container bg-gray-100 p-4 rounded-lg mb-4 h-96 overflow-y-auto">
        {conversation.length === 0 ? (
          <p className="text-gray-500">Commencez une conversation avec l'assistant...</p>
        ) : (
          conversation.map((msg) => (
            <div key={msg.id} className={`mb-2 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
              <div
                className={`inline-block p-3 rounded-lg max-w-xl whitespace-pre-wrap ${
                  msg.role === 'user'
                    ? 'bg-blue-500 text-white'
                    : msg.status === 'error'
                    ? 'bg-red-100 text-red-700 border border-red-300'
                    : msg.status === 'pending'
                    ? 'bg-gray-200 text-gray-600 animate-pulse'
                    : 'bg-white text-black'
                }`}
                aria-live={msg.status === 'pending' ? 'polite' : undefined}
              >
                {msg.content}
              </div>
            </div>
          ))
        )}
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Tapez votre message..."
          className="flex-1 p-2 border rounded"
          aria-label="Message"
        />
        <button
          onClick={handleSendMessage}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
          disabled={isSendDisabled}
        >
          {isLoading ? 'Envoi...' : 'Envoyer'}
        </button>
      </div>
    </main>
  );
}
