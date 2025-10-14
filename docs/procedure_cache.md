# Stratégie de cache Redis pour les procédures

Nous utilisons Redis pour mettre en cache deux lectures sensibles à la latence :

- `GET /procedures` : liste complète des procédures (avec leurs étapes).
- `GET /runs/{id}` : détail d'une exécution, y compris l'historique de commit des étapes.

## Clés et versionnement

Chaque payload est stocké sous une clé dérivée d'un compteur de version :

- Liste des procédures : `procedures:list:v{version}`.
- Détail d'un run : `procedures:run:{run_id}:v{version}`.

Les compteurs de version (`procedures:list:version`, `procedures:run:{run_id}:version`) sont
créés à la volée (`SETNX`) et incrémentés lors des invalidations. Cela garantit que toute
lecture postérieure utilisera une nouvelle clé et qu'aucun `DEL` massif n'est nécessaire.

## Invalidation

Les invalidations sont déclenchées automatiquement dans les handlers qui modifient les
entités :

- Création, mise à jour ou suppression d'une procédure → incrément du compteur global et de
  celui de la procédure.
- Création de run ou commit d'étape (`POST /runs/{id}/steps/{step_key}/commit`) → incrément du
  compteur associé au run.

Cette approche est **idempotente** et supporte des environnements multi-Workers : même si
plusieurs instances invalident simultanément, le compteur est simplement incrémenté plusieurs
fois et la clé effective change de suffixe.

## Instrumentation

Les métriques Prometheus suivantes sont exposées :

- `backend_procedure_cache_hits_total` / `backend_procedure_cache_misses_total`
- `backend_procedure_cache_store_total`
- `backend_procedure_cache_invalidations_total`
- `backend_procedure_cache_fetch_seconds` (labels `resource` et `source`)

Chaque opération produit également des logs structurés (`procedure_cache_hit`,
`procedure_cache_miss`, `procedure_cache_invalidated`) permettant de corréler la latence
observée côté client avec le comportement du cache.

## Dégradation

Si Redis est indisponible, les lectures retombent automatiquement sur la fonction de
rattrapage (`fetcher`) et un log d'avertissement est émis. Les opérations d'invalidation
échouées sont également loguées mais n'empêchent pas la réponse HTTP.
