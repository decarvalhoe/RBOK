'use client';

import { useCallback, useMemo, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';

import StatusBadge from './components/StatusBadge';
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

  if (error instanceof Error) {
    return `Erreur serveur: ${error.message}`;
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

  return 'Une erreur inconnue est survenue.';
};

export default function Home(): JSX.Element {
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

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

  const messageValue = watch('content') ?? '';
  const remainingCharacters = MESSAGE_MAX_LENGTH - messageValue.length;

  const isSendDisabled = useMemo(
    () => isLoading || isSubmitting || messageValue.trim().length === 0,
    [isLoading, isSubmitting, messageValue],
  );

  const appendMessage = useCallback((message: ConversationMessage) => {
    setConversation((previous) => [...previous, message]);
  }, []);

  const replacePendingMessage = useCallback(
    (pendingId: string, next: Partial<ConversationMessage>) => {
      setConversation((previous) =>
        previous.map((item) => (item.id === pendingId ? { ...item, ...next } : item)),
      );
    },
    [],
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

      appendMessage(userMessage);
      appendMessage(pendingMessage);
      setIsLoading(true);

      try {
        const response = await sendChatMessage(trimmedContent);
        const assistantContent = response?.content?.trim()
          ? response.content
          : "L'assistant n'a renvoyé aucun contenu.";

        replacePendingMessage(pendingMessage.id, {
          content: assistantContent,
          status: 'success',
        });
      } catch (error) {
        replacePendingMessage(pendingMessage.id, {
          content: getErrorMessage(error),
          status: 'error',
        });
      } finally {
        setIsLoading(false);
        reset({ content: '' });
      }
    },
    [appendMessage, isLoading, replacePendingMessage, reset],
  );

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        void handleSubmit(onSubmit)();
      }
    },
    [handleSubmit, onSubmit],
  );

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
      <header className="space-y-2 text-center">
        <StatusBadge label={isLoading ? 'Traitement en cours' : 'Prêt'} variant={isLoading ? 'info' : 'success'} />
        <h1 className="text-3xl font-semibold text-slate-900">Assistant procédural</h1>
        <p className="text-sm text-slate-600">
          Décrivez votre objectif et l&apos;assistant vous guidera étape par étape.
        </p>
      </header>

      <section
        aria-label="Historique de conversation"
        role="region"
        className="chat-container min-h-[240px] space-y-4 rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200"
      >
        {conversation.length === 0 ? (
          <p className="text-sm text-slate-500">
            Commencez la conversation en décrivant votre situation ou vos contraintes.
          </p>
        ) : (
          <ul className="space-y-3">
            {conversation.map((message) => (
              <li
                key={message.id}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-xl rounded-2xl px-4 py-3 text-sm shadow-sm ${
                    message.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : message.status === 'error'
                      ? 'bg-rose-100 text-rose-800 ring-1 ring-rose-200'
                      : message.status === 'pending'
                      ? 'bg-slate-100 text-slate-600'
                      : 'bg-slate-50 text-slate-900'
                  }`}
                  aria-live={message.status === 'pending' ? 'polite' : undefined}
                >
                  <p>{message.content}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <form
        className="flex flex-col gap-3 rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200 md:flex-row"
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
            aria-invalid={errors.content ? 'true' : 'false'}
            aria-describedby={errors.content ? 'message-error' : 'message-help'}
            {...register('content')}
            onKeyDown={handleKeyDown}
          />
          <div className="mt-1 flex flex-col gap-1">
            {errors.content ? (
              <p id="message-error" className="text-sm text-rose-600" role="alert">
                {errors.content.message}
              </p>
            ) : (
              <p id="message-help" className="text-sm text-slate-500">
                Votre message doit contenir entre {MESSAGE_MIN_LENGTH} et {MESSAGE_MAX_LENGTH} caractères.
              </p>
            )}
            <p aria-live="polite" className="text-xs text-slate-400">
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
