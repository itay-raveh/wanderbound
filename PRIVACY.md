# Privacy Policy

*Last updated: April 23, 2026*

Wanderbound is an open-source photo album generator. This policy covers what we collect, how we use it, and your rights.

## Data Controller

Each Wanderbound instance is independently operated. The person or organization running the instance you use is the data controller responsible for your data under applicable privacy laws (including the GDPR). The Wanderbound open-source project itself does not operate a hosted service and does not receive or process your data.

If you run your own Wanderbound instance, you are the data controller for your users and are responsible for your own privacy compliance.

## What We Collect

### Information You Provide

- **Account info** - When you sign in with Google or Microsoft, we receive your name, email address, and profile picture from the provider you choose. We create your account from this and display your name in the editor.
- **Polarsteps export data** - When you upload your Polarsteps data archive, we process your trips, steps, GPS coordinates, photos, and trip metadata to generate your album.
- **Google Photos access (optional)** - If you use the photo upgrade feature, we ask Google for read-only access through Google's own Picker UI. Only items you select in that picker are visible to us - your broader library is not. We download the original-resolution files for selected items to replace the lower-quality copies from your Polarsteps archive, and we store an encrypted refresh token so you can pick more items later without re-authorizing. The scope we request is `photospicker.mediaitems.readonly`.

### Information Collected Automatically

- **Session cookie** - We set a single HTTP-only cookie (`session`) to keep you signed in. It expires after 30 days. The service requires this cookie to function. We do not use advertising or marketing cookies.
- **Activity timestamps** - We record when you last used the service (roughly hourly). We use this to manage storage: when space runs low, the least-recently-active accounts lose files first (see Data Retention below).
- **Error reports and performance data** - We use [Sentry](https://sentry.io) to collect error reports and performance traces. Error reports include your browser type, operating system, error details, and a pseudonymous user identifier. When an error occurs, Sentry may capture a session replay - a recording of the page state that could include content visible on screen. Performance traces record page load times and API request durations.
- **Browser storage** - We store a few preferences in your browser's local storage (dark/light mode, last-viewed album). These stay on your device.

## Legal Basis for Processing

If you are in the EU, we process your data under these GDPR legal bases:

- **Contractual necessity** (Art. 6(1)(b)) - Account creation, trip processing, album generation, data export, and account deletion. These are the core operations you request when you use the service.
- **Legitimate interest** (Art. 6(1)(f)) - Error reporting, performance monitoring, activity timestamps, and storage management. We need these to keep the service running and to debug problems. You can opt out of Sentry by configuring your instance to disable it.
- **Consent** (Art. 6(1)(a)) - Signing in with Google or Microsoft. You choose your provider and can revoke access through their respective account settings.

## Third-Party Services

- **Google OAuth** - Handles sign-in if you choose Google. [Google's privacy policy](https://policies.google.com/privacy) applies.
- **Google Photos Picker (optional)** - When you use the photo upgrade feature, the server calls Google Photos Picker to retrieve metadata and download originals for items you picked. Only picker-selected items are accessible. [Google's privacy policy](https://policies.google.com/privacy) applies.
- **Microsoft OAuth** - Handles sign-in if you choose Microsoft. [Microsoft's privacy policy](https://privacy.microsoft.com/privacystatement) applies.
- **Mapbox** - Provides map tiles and routing data for album map pages. Your browser or the server sends GPS coordinates from your trip to Mapbox when you view or generate a map. [Mapbox's privacy policy](https://www.mapbox.com/legal/privacy) applies.
- **Open-Meteo** - Provides elevation and historical weather data. During album generation, the server sends your trip GPS coordinates and dates to Open-Meteo. [Open-Meteo's privacy policy](https://open-meteo.com/en/terms) applies.
- **OpenStreetMap Overpass** - Provides names and elevations for peaks near your hiking steps. During album generation, the server sends the coordinates of steps that look like local elevation peaks to Overpass. [OpenStreetMap privacy policy](https://osmfoundation.org/wiki/Privacy_Policy) applies.
- **Sentry** - Receives error reports, session replays, and performance traces as described above. [Sentry's privacy policy](https://sentry.io/privacy/) applies.

We do not share your data with other third parties, sell your data, or serve ads.

## Data Retention

The instance operator's server stores your uploaded data (photos, GPS tracks, trip metadata). We do not share data between instances or with other users.

When the server reaches storage capacity, we remove uploaded files (photos and media) starting with the least-recently-active accounts. Your account and album configuration survive, but you may need to re-upload your Polarsteps archive to restore the removed files. The instance operator sets the storage limits.

The instance operator controls the backup retention schedule.

## Security

We protect your data with HTTPS in transit, encrypted database backups, and application-level access controls that isolate each user's data. Sensitive tokens (such as Google Photos OAuth refresh tokens) are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256) using a key derived from the instance operator's `SECRET_KEY`. Uploaded files are stored in a directory structure keyed to your user ID and are not accessible to other users. The session cookie is HTTP-only and secure in production. For vulnerability reports, see [SECURITY.md](SECURITY.md).

## International Data Transfers

Your data may reach third-party services outside your country: Google, Microsoft, Mapbox, and Sentry operate in the United States; Open-Meteo operates in the European Union; the OpenStreetMap Foundation operates in the United Kingdom. If you are in the EU, these transfers rely on the standard contractual clauses each provider maintains.

## Children's Privacy

Wanderbound is not directed at children under the age of 16. We do not knowingly collect personal information from children. If you believe a child has provided personal data, contact the instance operator to have it removed.

## Your Rights

You can:

- **Delete your data** - Use "Delete all data" in the editor settings menu. This removes your account, albums, all uploaded files, and revokes any connected Google Photos access token on Google's side.
- **Export your data** - Use "Export my data" in the editor settings menu. You get a ZIP containing your account info, album configurations, photos, and videos (GDPR Article 20 data portability).
- **Correct your data** - Edit your name, locale, and preferences in the editor settings.

EU residents have additional rights under the GDPR, including the right to object to processing based on legitimate interest and the right to lodge a complaint with a supervisory authority. Data portability and deletion are in the editor settings menu. For other rights, contact the instance operator at the email address in the site footer.

## Changes to This Policy

We update this policy as the project evolves and commit changes to the project repository.

## Open Source

This project is open source. You can read the source code to see what data we collect and how we process it.

---

*Adapted from [Automattic's privacy policy](https://github.com/Automattic/legalmattic), licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).*
