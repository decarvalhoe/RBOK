import React from 'react';
import { FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { StackNavigationProp } from '@react-navigation/stack';
import { useNavigation } from '@react-navigation/native';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import { useProcedures } from '../api/hooks';
import { RootStackParamList } from '../navigation/types';

export type ProcedureListScreenNavigation = StackNavigationProp<
  RootStackParamList,
  'Procedures'
>;

export default function ProcedureListScreen() {
  const navigation = useNavigation<ProcedureListScreenNavigation>();
  const { data, isLoading, error, refetch, isRefetching } = useProcedures();

  const renderItem = React.useCallback(
    ({ item }: { item: { id: string; name: string; description: string } }) => (
      <TouchableOpacity
        style={styles.card}
        accessibilityRole="button"
        onPress={() => navigation.navigate('ProcedureDetail', { procedureId: item.id })}
      >
        <Text style={styles.cardTitle}>{item.name}</Text>
        <Text style={styles.cardDescription}>{item.description}</Text>
      </TouchableOpacity>
    ),
    [navigation]
  );

  if (isLoading) {
    return <LoadingState message="Chargement des procédures" />;
  }

  if (error) {
    return <ErrorState message="Impossible de récupérer les procédures." onRetry={refetch} />;
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={data ?? []}
        keyExtractor={(item) => item.id}
        renderItem={renderItem}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#2563eb" />
        }
        ListEmptyComponent={() => (
          <Text style={styles.emptyText}>Aucune procédure n'est disponible pour le moment.</Text>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f3f4f6',
  },
  listContent: {
    padding: 16,
  },
  card: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: 6,
    elevation: 2,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 8,
  },
  cardDescription: {
    fontSize: 14,
    color: '#4b5563',
  },
  emptyText: {
    textAlign: 'center',
    color: '#6b7280',
    marginTop: 24,
  },
});
