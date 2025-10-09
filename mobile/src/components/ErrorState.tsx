import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { logEvent } from '../analytics/logger';

type ErrorStateProps = {
  message?: string;
  onRetry?: () => void;
};

const ErrorState: React.FC<ErrorStateProps> = ({ message = 'Une erreur est survenue.', onRetry }) => {
  React.useEffect(() => {
    logEvent({ name: 'ui_error_state', properties: { message } });
  }, [message]);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Oups !</Text>
      <Text style={styles.description}>{message}</Text>
      {onRetry ? (
        <Text onPress={onRetry} style={styles.retry} accessibilityRole="button">
          Réessayer
        </Text>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
  },
  title: {
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 8,
  },
  description: {
    textAlign: 'center',
    color: '#4b5563',
    marginBottom: 12,
  },
  retry: {
    color: '#2563eb',
    fontWeight: '500',
  },
});

export default ErrorState;
