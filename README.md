# Trede Hub — site et version installable

## Lancer sur Windows
1. Installez Python 3.8 ou plus récent.
2. Double-cliquez sur `START_TREDE_HUB_WINDOWS.bat`.
3. Ouvrez `http://127.0.0.1:8000`.

Le site et l'API doivent toujours être lancés depuis ce même dossier : `server.py` sert `trede-hub.html` et les fichiers de l'application. N'utilisez pas un ancien `server.py` avec une nouvelle page HTML.

## Correction des logos et de l'espace Films
Le serveur et la page inclus sont appariés. Les champs `films_logo_url` et `footer_logo_1_url` à `footer_logo_6_url` sont enregistrés dans `site_content`. Après remplacement des fichiers, arrêtez l'ancien serveur (Ctrl+C dans sa fenêtre), démarrez celui de ce dossier, puis rechargez avec Ctrl+F5. Le serveur conserve la base dans `data/trede-hub.sqlite3` et les images dans `uploads/`.

Les vidéos de films MP4 et WebM qui dépassent la limite cible sont converties en MP4 H.264. La cible est de 4 Go au maximum, ou la place disponible sur le disque si elle est moindre. La compression garde le 4K lorsque le débit le permet; sinon elle passe en 1080p ou 720p. Le fichier original temporaire est supprimé après la conversion. Le disque doit pouvoir contenir le fichier original pendant la compression et la vidéo finale. `START_TREDE_HUB_WINDOWS.bat` installe `imageio-ffmpeg` au premier démarrage si nécessaire; une connexion Internet est alors requise.

## Installer comme application
Le projet inclut une Progressive Web App (PWA): `manifest.webmanifest`, `service-worker.js` et les icônes.
- Android: ouvrez l'adresse publique HTTPS dans Chrome puis choisissez « Installer l'application » / « Ajouter à l'écran d'accueil ».
- iPhone: ouvrez l'adresse publique HTTPS dans Safari, choisissez Partager puis « Sur l'écran d'accueil ».
- Windows/macOS: ouvrez l'adresse publique HTTPS dans un navigateur compatible et choisissez Installer.

**Important:** `127.0.0.1` est seulement votre propre ordinateur; les autres personnes ne peuvent pas accéder à ce serveur depuis leurs téléphones. Pour une installation à distance, le site doit être déployé sur un hébergement HTTPS. Ce paquet ne contient pas un APK Android natif ni un installateur Windows `.exe`; il prépare l'application web installable.

## Données
Les données du catalogue, les comptes et les réglages sont dans `data/trede-hub.sqlite3`; les médias sont dans `uploads/`. Sauvegardez ces deux éléments avant toute mise à jour. Le serveur par défaut est local et ne doit pas être exposé directement à Internet sans déploiement sécurisé.
