import React from 'react';
import { RouteProp, useNavigation, useRoute } from '@react-navigation/native';
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { StackNavigationProp } from '@react-navigation/stack';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import { RootStackParamList } from '../navigation/types';
import { useProcedure, useStartProcedureRun } from '../api/hooks';

export type ProcedureDetailRoute = RouteProp<RootStackParamList, 'ProcedureDetail'>;
type ProcedureDetailNavigation = StackNavigationProp<RootStackParamList, 'ProcedureDetail'>;

export default function ProcedureDetailScreen() {
  const route = useRoute<ProcedureDetailRoute>();
  const navigation = useNavigation<ProcedureDetailNavigation>();
  const { procedureId } = route.params;
  const { data, isLoading, error, refetch, isFetching } = useProcedure(procedureId);
  const startRun = useStartProcedureRun(procedureId);

  const handleStart = React.useCallback(async () => {
    try {
      const run = await startRun.mutateAsync();
      navigation.navigate('Conversation', { procedureId, runId: run.id });
    } catch (err) {
      // erreurs déjà journalisées via analytics
    }
  }, [navigation, procedureId, startRun]);

  if (isLoading) {
    return <LoadingState message="Chargement de la procédure" />;
  }

  if (error || !data) {
    return <ErrorState message="Impossible de charger cette procédure." onRetry={refetch} />;
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{data.name}</Text>
      <Text style={styles.description}>{data.description}</Text>

      <TouchableOpacity
        onPress={handleStart}
        accessibilityRole="button"
        style={[styles.primaryButton, (startRun.isPending || isFetching) && styles.buttonDisabled]}
        disabled={startRun.isPending || isFetching}
      >
        {startRun.isPending ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.primaryButtonText}>Démarrer une conversation</Text>
        )}
      </TouchableOpacity>

      <Text style={styles.sectionTitle}>Étapes</Text>
      <FlatList
        data={data.steps}
        keyExtractor={(item) => item.key}
        contentContainerStyle={styles.list}
        renderItem={({ item, index }) => (
          <View style={styles.stepCard}>
            <Text style={styles.stepIndex}>Étape {index + 1}</Text>
            <Text style={styles.stepTitle}>{item.title}</Text>
            <Text style={styles.stepPrompt}>{item.prompt || 'Prompt indisponible hors-ligne.'}</Text>
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
    backgroundColor: '#ffffff',
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    marginBottom: 8,
  },
  description: {
    color: '#4b5563',
    marginBottom: 16,
  },
  primaryButton: {
    backgroundColor: '#2563eb',
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
    marginBottom: 24,
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  primaryButtonText: {
    color: '#fff',
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 12,
  },
  list: {
    gap: 12,
    paddingBottom: 32,
  },
  stepCard: {
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 12,
    padding: 16,
  },
  stepIndex: {
    fontWeight: '600',
    color: '#6b7280',
  },
  stepTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginVertical: 4,
  },
  stepPrompt: {
    color: '#4b5563',
  },
});
