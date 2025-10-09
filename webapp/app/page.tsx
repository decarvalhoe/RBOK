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
  const handleSendMessage = async () => {
    if (!message.trim()) return;

    const newMessage = { role: 'user', content: message };
    setConversation(prev => [...prev, newMessage]);
    setMessage('');

    // TODO: Intégrer avec l'API backend
    const response = { role: 'assistant', content: 'Réponse de l\'assistant (à implémenter)' };
    setConversation(prev => [...prev, response]);
  };

  return (
    <main className="container mx-auto flex min-h-screen flex-col gap-6 p-6">
      <header className="space-y-2 text-center">
        <p className="text-sm uppercase tracking-wide text-blue-600">Prototype</p>
        <h1 className="text-3xl font-bold text-slate-900 md:text-4xl">
          Assistant Procédural "Réalisons" v0.1
        </h1>
        <p className="text-base text-slate-600">
          Expérimentez la prochaine génération d'assistant procédural intelligent.
        </p>
      </header>

      <section
        aria-label="Historique de conversation"
        className="chat-container flex-1 rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200"
      >
        {conversation.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center text-slate-500">
            <p className="text-lg font-medium">Commencez une conversation avec l'assistant…</p>
            <p className="text-sm">Partagez un objectif et laissez l'IA vous guider étape par étape.</p>
          </div>
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
          <div className="flex h-full flex-col gap-3 overflow-y-auto">
            {conversation.map((msg, index) => (
              <div
                key={index}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-lg rounded-2xl px-4 py-3 text-sm shadow-sm ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-100 text-slate-900'
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex gap-2">
      </section>

      <form
        className="flex flex-col gap-3 rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200 md:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          handleSendMessage();
        }}
      >
        <label className="sr-only" htmlFor="message">
          Message
        </label>
        <input
          id="message"
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
          placeholder="Tapez votre message..."
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-base shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
        />
        <button
          type="submit"
          className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-base font-semibold text-white transition hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/60"
        >
          {isLoading ? 'Envoi...' : 'Envoyer'}
        </button>
      </form>
    </main>
  );
}
