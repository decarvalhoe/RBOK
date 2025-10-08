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
    <main className="container mx-auto p-4">
      <h1 className="text-3xl font-bold mb-6">Assistant Procédural "Réalisons" v0.1</h1>
      
      <div className="chat-container bg-gray-100 p-4 rounded-lg mb-4 h-96 overflow-y-auto">
        {conversation.length === 0 ? (
          <p className="text-gray-500">Commencez une conversation avec l'assistant...</p>
        ) : (
          conversation.map((msg, index) => (
            <div key={index} className={`mb-2 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
              <div className={`inline-block p-2 rounded ${
                msg.role === 'user' ? 'bg-blue-500 text-white' : 'bg-white text-black'
              }`}>
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
          onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
          placeholder="Tapez votre message..."
          className="flex-1 p-2 border rounded"
        />
        <button
          onClick={handleSendMessage}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Envoyer
        </button>
      </div>
    </main>
  );
}
