'use client';

import { useCallback, useMemo, useState } from 'react';
import type { KeyboardEvent } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';

import { sendChatMessage } from '../lib/api';
import { MESSAGE_MAX_LENGTH, MESSAGE_MIN_LENGTH } from '../lib/messageConstraints';

type MessageStatus = 'pending' | 'success' | 'error';

type ConversationMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  status: MessageStatus;
};

const PENDING_TEXT = 'Assistant est en train de répondre...';

const messageSchema = z.object({
  content: z
    .string()
    .trim()
    .min(
      MESSAGE_MIN_LENGTH,
      `Le message doit contenir au moins ${MESSAGE_MIN_LENGTH} caractère${
        MESSAGE_MIN_LENGTH > 1 ? 's' : ''
      }`,
    )
    .max(
      MESSAGE_MAX_LENGTH,
      `Le message ne peut pas dépasser ${MESSAGE_MAX_LENGTH} caractères.`,
    ),
});

type MessageFormValues = z.infer<typeof messageSchema>;

const getErrorMessage = (error: unknown): string => {
  if (typeof error === 'string') {
    return error;
  }

  if (error && typeof error === 'object' && 'response' in error) {
    const response = (
      error as {
        response?: { data?: { detail?: string; message?: string }; status?: number };
      }
    ).response;
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

export default function Home(): JSX.Element {
  const [message, setMessage] = useState('');
export default function Home() {
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const isSendDisabled = useMemo(() => isLoading || !message.trim(), [isLoading, message]);

  const handleSendMessage = useCallback(async () => {
    const trimmed = message.trim();
    if (!trimmed || isLoading) {
    if (isLoading || !message.trim()) {
      return;
    }

    const userMessage: ConversationMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
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
      const response = await sendChatMessage(trimmed);
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
          msg.id === pendingMessage.id ? { ...msg, content: errorMessage, status: 'error' } : msg,
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
        void handleSendMessage();
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<MessageFormValues>({
    resolver: zodResolver(messageSchema),
    defaultValues: { content: '' },
    mode: 'onChange',
  });

  const messageValue = watch('content');
  const currentLength = messageValue?.length ?? 0;
  const remainingCharacters = MESSAGE_MAX_LENGTH - currentLength;

  const isSendDisabled = useMemo(
    () => isLoading || isSubmitting || !(messageValue && messageValue.trim().length > 0),
    [isLoading, isSubmitting, messageValue],
  );

  const onSubmit = useCallback(
    async ({ content }: MessageFormValues) => {
      if (isLoading) {
        return;
      }

      const trimmedContent = content.trim();
      const timestamp = Date.now();

      const userMessage: ConversationMessage = {
        id: `user-${timestamp}`,
        role: 'user',
        content: trimmedContent,
        status: 'success',
      };

      const pendingMessage: ConversationMessage = {
        id: `assistant-${timestamp}`,
        role: 'assistant',
        content: PENDING_TEXT,
        status: 'pending',
      };

      setConversation((prev) => [...prev, userMessage, pendingMessage]);
      setIsLoading(true);
      reset({ content: '' });

      try {
        const response = await sendChatMessage(trimmedContent);
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
    },
    [isLoading, reset, setConversation, setIsLoading],
  );

  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      void handleSendMessage();
    },
    [handleSendMessage],
  );

  return (
    <main className="container mx-auto flex min-h-screen flex-col gap-6 p-6">
      <header className="space-y-2 text-center">
        <p className="text-sm uppercase tracking-wide text-blue-600">Prototype</p>
        <h1 className="text-3xl font-bold text-slate-900 md:text-4xl">
          Assistant Procédural &quot;Réalisons&quot; v0.1
        </h1>
        <p className="text-base text-slate-600">
          Expérimentez la prochaine génération d&apos;assistant procédural intelligent.
        </p>
      </header>

      <section
        aria-label="Historique de conversation"
        className="flex-1 overflow-hidden rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200"
      >
        {conversation.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-slate-500">
            <p className="text-lg font-medium">Commencez une conversation avec l&apos;assistant…</p>
            <p className="text-sm">
              Partagez un objectif et laissez l&apos;IA vous guider étape par étape.
            </p>
          </div>
        ) : (
          <ul className="flex h-full flex-col gap-3 overflow-y-auto">
            {conversation.map((msg) => (
              <li
          <div className="flex h-full flex-col gap-3 overflow-y-auto">
            {conversation.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-lg rounded-2xl px-4 py-3 text-sm shadow-sm ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : msg.status === 'error'
                      ? 'bg-red-100 text-red-700 border border-red-300'
                      : msg.status === 'pending'
                      ? 'bg-gray-200 text-gray-600 animate-pulse'
                        ? 'bg-red-100 text-red-700 ring-1 ring-red-200'
                        : msg.status === 'pending'
                          ? 'bg-slate-100 text-slate-600'
                          : 'bg-slate-50 text-slate-900'
                      ? 'bg-red-100 text-red-700 border border-red-300'
                      : msg.status === 'pending'
                      ? 'bg-slate-200 text-slate-600'
                      : 'bg-slate-100 text-slate-900'
                  }`}
                  aria-live={msg.status === 'pending' ? 'polite' : undefined}
                >
                  <p>{msg.content}</p>
                  {msg.status === 'pending' && (
                    <span className="mt-2 block text-xs text-slate-500">Réponse en cours…</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <form
        className="flex flex-col gap-3 rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200 md:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          handleSendMessage();
        }}
        onSubmit={handleSubmit}
      >
        <label className="sr-only" htmlFor="message">
          Message
        </label>
        <input
          id="message"
          type="text"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Tapez votre message..."
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-base shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
          aria-label="Message"
        />
        <button
          type="submit"
          className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-base font-semibold text-white transition hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/60 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={isLoading}
        />
        <button
          type="submit"
          className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-base font-semibold text-white transition hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/60 disabled:cursor-not-allowed disabled:opacity-60"
        onSubmit={handleSubmit(onSubmit)}
        noValidate
      >
        <div className="flex-1">
          <label className="sr-only" htmlFor="message">
            Message
          </label>
          <input
            id="message"
            type="text"
            placeholder="Décrivez votre objectif..."
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-base shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            aria-label="Message"
            aria-invalid={errors.content ? 'true' : 'false'}
            aria-describedby={errors.content ? 'message-error' : 'message-help'}
            {...register('content')}
          />
          <div className="mt-1 flex flex-col gap-1">
            {errors.content ? (
              <p
                id="message-error"
                className="text-sm text-red-600"
                role="alert"
                aria-live="polite"
              >
                {errors.content.message}
              </p>
            ) : (
              <p id="message-help" className="text-sm text-slate-500">
                Votre message doit contenir entre {MESSAGE_MIN_LENGTH} et {MESSAGE_MAX_LENGTH} caractères.
              </p>
            )}
            <p
              aria-live="polite"
              className="text-xs text-slate-400"
            >
              {remainingCharacters >= 0
                ? `${remainingCharacters} caractères restants`
                : `${Math.abs(remainingCharacters)} caractères au-delà de la limite`}
            </p>
          </div>
        </div>
        <button
          type="submit"
          className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-base font-semibold text-white transition hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/60 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={isSendDisabled}
        >
          {isLoading ? 'Envoi...' : 'Envoyer'}
        </button>
      </form>
    </main>
  );
}
