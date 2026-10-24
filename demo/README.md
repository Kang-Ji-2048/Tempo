# Tempo browser demo deck

Open `index.html` directly or serve it as a static page. It has no dependencies, external fonts, trackers or backend requests.

- Arrow keys, Page Up/Down or Space change slides.
- N toggles presenter notes. Notes are public presentation content, not secret data.
- F toggles fullscreen where the browser permits it.
- Home/End jump to the first/last slide.
- `#6` links directly to the real-video check.
- Browser Print creates a landscape slide handout with all slides.

To add it to a Vercel site:

- Next.js or Vite: copy this directory to the site's `public/demo/` directory and link to `/demo/`.
- A plain static website: copy this directory to `demo/` in the published root.
- A standalone Vercel project: publish this directory with framework preset Other and no build command.

No deployment configuration is included, so the deck will not override an existing site's routing or build settings.

The site URL/source is still needed to integrate and publish it in the intended project. Update readiness statements before the actual demo if deployment, API mode or model quota changes.
