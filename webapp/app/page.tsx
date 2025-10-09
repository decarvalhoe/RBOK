'use client';

import { useState } from 'react';

export default function Home() {
  const [message, setMessage] = useState('');
  const [conversation, setConversation] = useState<Array<{role: string, content: string}>>([]);

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
          placeholder="Tapez votre message..."
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-base shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
        />
        <button
          type="submit"
          className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-base font-semibold text-white transition hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/60"
        >
          Envoyer
        </button>
      </form>
    </main>
  );
}
