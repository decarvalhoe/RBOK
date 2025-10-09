import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { StackNavigationProp } from '@react-navigation/stack';
import { useNavigation } from '@react-navigation/native';
import { RootStackParamList } from '../navigation/types';

type HomeScreenNavigation = StackNavigationProp<RootStackParamList, 'Home'>;

export default function HomeScreen() {
  const navigation = useNavigation<HomeScreenNavigation>();

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Assistant « Réalisons »</Text>
      <Text style={styles.subtitle}>
        Retrouvez vos procédures, synchronisez vos sessions et poursuivez vos conversations même
        hors connexion.
      </Text>

      <TouchableOpacity
        accessibilityRole="button"
        onPress={() => navigation.navigate('Procedures')}
        style={styles.primaryButton}
      >
        <Text style={styles.primaryButtonText}>Explorer les procédures</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
    backgroundColor: '#f9fafb',
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    marginBottom: 16,
  },
  subtitle: {
    fontSize: 16,
    color: '#4b5563',
    textAlign: 'center',
    marginBottom: 32,
  },
  primaryButton: {
    backgroundColor: '#2563eb',
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 8,
  },
  primaryButtonText: {
    color: '#ffffff',
    fontWeight: '600',
    fontSize: 16,
  },
});
