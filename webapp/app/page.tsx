'use client';

import { useCallback, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
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
    .max(MESSAGE_MAX_LENGTH, `Le message ne peut pas dépasser ${MESSAGE_MAX_LENGTH} caractères.`),
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

export default function Home() {
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
            msg.id === pendingMessage.id ? { ...msg, content: errorMessage, status: 'error' } : msg,
          ),
        );
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, reset, setConversation, setIsLoading],
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
            <p className="text-sm">Partagez un objectif et laissez l&apos;IA vous guider étape par étape.</p>
          </div>
        ) : (
          <ul className="flex h-full flex-col gap-3 overflow-y-auto">
            {conversation.map((msg) => (
              <li
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-lg rounded-2xl px-4 py-3 text-sm shadow-sm ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : msg.status === 'error'
                        ? 'border border-red-300 bg-red-50 text-red-900'
                        : 'border border-slate-200 bg-slate-50 text-slate-900'
                  }`}
                >
                  <p className="whitespace-pre-wrap break-words leading-relaxed">
                    {msg.status === 'pending' && msg.role === 'assistant' ? (
                      <span className="italic text-slate-600">{msg.content}</span>
                    ) : (
                      msg.content
                    )}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <form
        onSubmit={handleSubmit(onSubmit)}
        className="flex flex-col gap-3 rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200"
      >
        <div className="flex flex-col gap-1">
          <label htmlFor="message-input" className="text-sm font-medium text-slate-700">
            Votre message
          </label>
          <textarea
            {...register('content')}
            id="message-input"
            rows={3}
            placeholder="Saisissez votre message ici..."
            disabled={isLoading || isSubmitting}
            className="resize-none rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500"
          />
          <div className="flex items-center justify-between text-xs">
            <div>
              {errors.content && <span className="text-red-600">{errors.content.message}</span>}
            </div>
            <span
              className={`${
                remainingCharacters < 50 ? 'text-amber-600' : 'text-slate-500'
              } ${remainingCharacters < 0 ? 'text-red-600' : ''}`}
            >
              {currentLength}/{MESSAGE_MAX_LENGTH}
            </span>
          </div>
        </div>

        <button
          type="submit"
          disabled={isSendDisabled}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
        >
          {isLoading || isSubmitting ? 'Envoi en cours...' : 'Envoyer'}
        </button>
      </form>
    </main>
  );
}
