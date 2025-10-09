import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

type LoadingStateProps = {
  message?: string;
};

const LoadingState: React.FC<LoadingStateProps> = ({ message = 'Chargement...' }) => (
  <View style={styles.container}>
    <ActivityIndicator size="large" color="#2563eb" />
    <Text style={styles.message}>{message}</Text>
  </View>
);

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
  },
  message: {
    marginTop: 12,
    fontSize: 16,
    color: '#1f2937',
  },
});

export default LoadingState;
