# Procédure de QA manuelle WebRTC

Ce guide décrit une séquence de test manuelle pour valider la négociation d'une session WebRTC via
les nouvelles API de signalisation.

## Pré-requis

- Deux navigateurs récents (ou un navigateur et un script `curl`).
- Le backend FastAPI démarré avec la base de données migrée.
- Les variables d'environnement `WEBRTC_STUN_SERVERS` / `WEBRTC_TURN_SERVERS` renseignées si un
  serveur TURN/STUN est requis dans votre environnement réseau.

## Étapes

1. **Créer une session** depuis le premier navigateur via l'interface `/webrtc` :
   - Autorisez l'accès à la caméra et au microphone.
   - Copiez l'identifiant de session généré.
2. **Récupérer l'offre SDP** depuis un second poste :
   - Exécutez `curl http://localhost:8000/webrtc/sessions/<session_id>`.
   - Notez la valeur `offer_sdp`.
3. **Fournir une réponse SDP** :
   - Générez une réponse via un second navigateur ou un client WebRTC séparé.
   - Envoyez-la avec `curl -X POST http://localhost:8000/webrtc/sessions/<session_id>/answer \
     -H 'Content-Type: application/json' \
     -d '{"responder_id": "peer-b", "answer_sdp": "<votre_sdp>", "responder_metadata": {"role": "helper"}}'`.
4. **Échanger des candidats ICE** :
   - Les navigateurs publieront automatiquement leurs candidats via l'interface.
   - Utilisez `/webrtc/sessions/<id>` pour vérifier la liste consolidée.
5. **Valider la connexion** :
   - Le statut doit passer à `answered` et la vidéo distante apparaître sur le premier navigateur.
   - Terminez en appelant `/webrtc/sessions/<id>/close` pour archiver la session.

## Résultats attendus

- Le backend persiste les informations de session et retourne les données mises à jour à chaque
  étape.
- Les erreurs d'autorisation média ou de réseau sont remontées dans l'interface web sous forme de
  messages clairs.
- Les commandes `curl` peuvent être intégrées dans un pipeline CI pour automatiser partiellement la
  validation si besoin.
