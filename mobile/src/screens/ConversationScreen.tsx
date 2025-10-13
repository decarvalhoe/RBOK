import React from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  FlatList,
} from 'react-native';
import { RouteProp, useRoute } from '@react-navigation/native';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import { RootStackParamList } from '../navigation/types';
import { useProcedure, useRun } from '../api/hooks';
import {
  ConversationMessage,
  ConversationSession,
  appendMessage,
  getSession,
} from '../storage/sessionStore';

export type ConversationRoute = RouteProp<RootStackParamList, 'Conversation'>;

type ConversationListItem = ConversationMessage & { key: string };

export default function ConversationScreen() {
  const route = useRoute<ConversationRoute>();
  const { procedureId, runId } = route.params;

  const { data: procedure, isLoading: isProcedureLoading, error: procedureError, refetch } =
    useProcedure(procedureId);
  const { data: run } = useRun(runId);

  const [message, setMessage] = React.useState('');
  const [session, setSession] = React.useState<ConversationSession | null>(() =>
    getSession(runId)
  );
  const [isResponding, setIsResponding] = React.useState(false);
  const listRef = React.useRef<FlatList<ConversationListItem>>(null);

  React.useEffect(() => {
    if (!session) {
      const restored = getSession(runId);
      if (restored) {
        setSession(restored);
      }
    }
  }, [runId, session]);

  const handleSend = React.useCallback(() => {
    if (!message.trim()) {
      return;
    }

    const userMessage: ConversationMessage = {
      id: `${runId}-user-${Date.now()}`,
      role: 'user',
      content: message.trim(),
      createdAt: new Date().toISOString(),
    };

    const updated = appendMessage(runId, userMessage, procedureId);
    setSession(updated);
    requestAnimationFrame(() => {
      listRef.current?.scrollToEnd({ animated: true });
    });
    setMessage('');
    setIsResponding(true);

    setTimeout(() => {
      const assistantCount = updated.messages.filter((msg) => msg.role === 'assistant').length;
      const nextStepIndex = Math.max(assistantCount - 1, 0);
      const nextStep = procedure?.steps?.[nextStepIndex];
      const response = nextStep
        ? `${nextStep.title}\n${nextStep.prompt}`
        : "Merci pour votre retour. Nous reviendrons vers vous très vite.";

      const assistantMessage: ConversationMessage = {
        id: `${runId}-assistant-${Date.now()}`,
        role: 'assistant',
        content: response,
        createdAt: new Date().toISOString(),
      };

      const finalSession = appendMessage(runId, assistantMessage, procedureId);
      setSession(finalSession);
      setIsResponding(false);
      requestAnimationFrame(() => {
        listRef.current?.scrollToEnd({ animated: true });
      });
    }, 350);
  }, [message, procedure?.steps, procedureId, runId]);

  if (isProcedureLoading && !session) {
    return <LoadingState message="Chargement de la conversation" />;
  }

  if (procedureError && !session) {
    return (
      <ErrorState
        message="Impossible de récupérer les détails de la procédure."
        onRetry={refetch}
      />
    );
  }

  const messages: ConversationListItem[] = (session?.messages ?? []).map((item) => ({
    ...item,
    key: item.id,
  }));

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={80}
    >
      <View style={styles.header}>
        <Text style={styles.headerTitle}>{procedure?.name ?? 'Conversation'}</Text>
        <Text style={styles.headerSubtitle}>Session #{run?.id.slice(0, 8) ?? runId}</Text>
      </View>

      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(item) => item.key}
        contentContainerStyle={styles.messages}
        renderItem={({ item }) => (
          <View
            style={[
              styles.messageBubble,
              item.role === 'user' ? styles.userBubble : styles.assistantBubble,
            ]}
          >
            <Text style={styles.messageText}>{item.content}</Text>
            <Text style={styles.messageMeta}>
              {new Date(item.createdAt).toLocaleTimeString('fr-FR', {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </Text>
          </View>
        )}
        ListEmptyComponent={() => (
          <Text style={styles.emptyState}>Commencez la discussion en envoyant un message.</Text>
        )}
      />

      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          placeholder="Votre message..."
          value={message}
          onChangeText={setMessage}
          editable={!isResponding}
          accessibilityLabel="Champ de saisie pour la conversation"
        />
        <TouchableOpacity
          style={[styles.sendButton, (isResponding || !message.trim()) && styles.sendButtonDisabled]}
          onPress={handleSend}
          disabled={isResponding || !message.trim()}
          testID="send-button"
        >
          <Text style={styles.sendButtonText}>{isResponding ? '...' : 'Envoyer'}</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f9fafb',
  },
  header: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 8,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '700',
  },
  headerSubtitle: {
    color: '#6b7280',
  },
  messages: {
    padding: 16,
    gap: 12,
  },
  emptyState: {
    textAlign: 'center',
    color: '#6b7280',
    marginTop: 24,
  },
  messageBubble: {
    maxWidth: '80%',
    borderRadius: 12,
    padding: 12,
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: '#2563eb',
  },
  assistantBubble: {
    alignSelf: 'flex-start',
    backgroundColor: '#e5e7eb',
  },
  messageText: {
    color: '#111827',
  },
  messageMeta: {
    fontSize: 10,
    marginTop: 4,
    color: '#6b7280',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    backgroundColor: '#ffffff',
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
    gap: 8,
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 999,
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: '#fff',
  },
  sendButton: {
    backgroundColor: '#2563eb',
    paddingVertical: 10,
    paddingHorizontal: 18,
    borderRadius: 999,
  },
  sendButtonDisabled: {
    opacity: 0.5,
  },
  sendButtonText: {
    color: '#fff',
    fontWeight: '600',
  },
});
