# AppLinkr

AppLinkr is a simple yet powerful web application that generates a QR code and forwards users to the appropriate App Store or Google Play Store based on their device type. With AppLinkr, you can easily share your mobile application links and track user interactions.

## Demo

Test out **AppLinkr** at [https://demo.applinkr.one](https://demo.applinkr.one)

Admin password: `applinkr-demo` 

The database will reset every 24 hours.


## Features

- **QR Code Generation**: Generate a unique QR code for your app with a simple interface.
- **Device Detection**: Automatically redirects users to the appropriate app store based on their device (iOS or Android).
- **Tracking**: Monitor user interactions with each QR code, including access count and device type.
- **Admin Panel**: View statistics, manage QR codes, and download the database backup.


## Roadmap

- Enhance stats with graphs
- Improve UI design
- Individualize QR-codes with frames and embedded images 

**Hint:** *If you are interested in contributing to AppLinkr, feel free to do so. It would help me a lot.*

## Installation (via docker-compose)

```yaml
version: '3.8'

services:
  applinkr:
    image: schech1/applinkr:latest
    ports:
      - "5001:5001"
    environment:
      PASSWORD: admin
      SERVER_URL: "https://qr.domain.com"
    volumes:
      - ./db:/app/db
```

## Deployment to Vercel (Serverless)

You can deploy AppLinkr on [Vercel](https://vercel.com/) using the included `vercel.json` configuration. The deployment runs the Flask app through Vercel's Python runtime.

### Steps
1. **Install the Vercel CLI** (if you want to deploy from your machine):
   ```bash
   npm i -g vercel
   ```
2. **Set environment variables** in the Vercel dashboard (Project Settings → Environment Variables):
   - `PASSWORD`: admin password for the `/admin` panel.
   - `SERVER_URL`: the public URL of your deployment (e.g., `https://your-app.vercel.app`).
3. **Deploy** from the repository root:
   ```bash
   vercel --prod
   ```

The `vercel.json` routes all requests to `api/index.py`, which exposes the Flask application. Dependencies are installed via the root `requirements.txt` (which references `app/requirements.txt`).

## Usage
Navigate to your domain, to open the QR-Code-Generator.

Navigate to `/admin` to access the admin panel. Login with your defined password.

## Contributing

### Help Wanted
I'm looking for someone with UI/UX-Experience to improve the design of the app. 
If you are interested to contribute, let me know.
