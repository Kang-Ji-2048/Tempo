# Demo room

A responsive, static video page prepared for Vercel. No build or dependency installation is required.

## Add the WhatsApp recording

1. Download the recording from WhatsApp.
2. Put the video in this folder as `demo.mp4`.
3. In `config.js`, set `videoUrl: 'demo.mp4'` and edit the title and description.

The repository ignores MP4 files by default. To publish this specific recording with Git, explicitly add it with `git add -f demo-video/demo.mp4` from the repository root. Prefer external video hosting for large files.

For large recordings, use a direct HTTPS video file URL in `config.js` instead. A WhatsApp conversation or share URL cannot be used as the video source.

The current recording is `demo.mp4`, prepared from the supplied My Movie 3.mp4 as a web-optimized H.264/AAC MP4 with fast-start playback. YouTube watch, share, Shorts, and embed links are also supported if needed later.

## Preview

Run `npm start` from this folder, then open `http://127.0.0.1:3000`.
You can also open `index.html` directly for a basic preview.

The video picker and drag-and-drop work locally. They do not upload the file or publish it to visitors. Customization in the page is stored only in that browser; edit `config.js` for shared settings.

## Publish

Deploy this folder as a static site to your Vercel account, using the Vercel CLI or a connected Git repository. Select the Other framework preset, root directory `demo-video`, output directory `.`, and no build or install command. The local `vercel.json` contains the static deployment settings.

The page plays the bundled recording using the browser's native video player, with seeking, sound, and fullscreen controls.

## Checks completed

- JavaScript syntax checks passed.
- Desktop browser preview loaded successfully.
- Customization dialog opened and saved settings successfully.
- No browser console errors during these checks.

Typography uses Google Fonts, with local sans-serif fallbacks.
