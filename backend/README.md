# Réalisons Backend

## Variables d'environnement

| Nom | Description | Valeur par défaut | Recommandations |
| --- | ----------- | ----------------- | ---------------- |
| `REALISONS_SECRET_KEY` | Clef secrète pour signer les JWT. | *(obligatoire)* | Générer une valeur aléatoire de 32+ octets, la stocker dans un coffre à secrets et la faire tourner régulièrement. |
| `DATABASE_URL` | Chaîne de connexion complète vers la base de données. | `None` | Préférer une URL complète en production (ex : `postgresql+psycopg://`). |
| `DB_DRIVER` | Driver SQLAlchemy (si `DATABASE_URL` absent). | `postgresql` | Peut être `sqlite`, `postgresql`, etc. |
| `DB_HOST` | Hôte de la base de données. | `localhost` | Ne pas exposer publiquement ; utiliser un réseau privé. |
| `DB_PORT` | Port de la base de données. | `5432` | Restreindre via firewall / security groups. |
| `DB_NAME` | Nom de la base. | `rbok` ou `rbok.db` pour SQLite. | Utiliser des noms différents selon les environnements. |
| `DB_USER` | Utilisateur de la base. | `rbok` | S'assurer que chaque environnement possède son propre utilisateur. |
| `DB_PASSWORD` | Mot de passe de la base. | `rbok` | Gérer via un secret manager et activer la rotation régulière. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durée de vie des tokens JWT. | `60` | Réduire pour limiter l'impact d'une compromission. |
| `WEBRTC_STUN_SERVERS` | Liste séparée par virgules des URLs STUN. | `""` | Fournir au moins un serveur public ou interne. |
| `WEBRTC_TURN_SERVERS` | Liste séparée par virgules des URLs TURN. | `""` | Obligatoire derrière des pare-feux restrictifs. |
| `WEBRTC_TURN_USERNAME` | Identifiant TURN partagé avec les clients. | `None` | Stocker dans un secret manager. |
| `WEBRTC_TURN_PASSWORD` | Mot de passe TURN. | `None` | Transmettre via un canal chiffré uniquement. |

### Bonnes pratiques
- Copier `.env.example` vers `.env` et définir des valeurs uniques par environnement.
- Le backend refusera de démarrer si `REALISONS_SECRET_KEY` est absent ou égale à la valeur de développement par défaut.
- Prévoir un processus de rotation (Vault, AWS Secrets Manager, etc.) et documenter la procédure.
- Ne jamais committer `backend/.env`.

## Exécution locale
```bash
cp .env.example .env
# éditer .env
uvicorn app.main:app --reload --port 8000
```

Le point d'extrémité `/healthz` fournit un statut simple indiquant si les variables critiques sont présentes.

## Tests de fumée

### Validation des migrations Alembic

Un test Pytest (`pytest -m migrations`) exécute `alembic upgrade head` sur une base en mémoire et compare le schéma obtenu avec les modèles SQLAlchemy du dossier `app/models`. Aucun service externe n'est requis : le test force `DATABASE_URL=sqlite+pysqlite:///:memory:` pendant son exécution.

Pour reproduire le comportement avec une autre base (par exemple PostgreSQL), positionnez la variable d'environnement `DATABASE_URL` avant d'invoquer `pytest`. Assurez-vous également que les dépendances spécifiques (drivers comme `psycopg` pour PostgreSQL) sont installées, faute de quoi le test sera automatiquement ignoré.
