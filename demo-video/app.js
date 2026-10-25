(() => {
  const $ = id => document.getElementById(id);
  let config = {...window.DEMO_CONFIG};
  try { config = {...config, ...JSON.parse(localStorage.getItem('demo-room-settings') || '{}')}; } catch {}
  let objectUrl;
  let toastTimer;
  function toast(message) {
    $('toast').textContent = message; $('toast').hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 6000);
  }
  function showVideo(url, local = false) {
    $('video').pause();
    $('youtube').hidden = true; $('youtube').removeAttribute('src'); $('videoSource').hidden = true;
    let youtubeId;
    try {
      const parsed = new URL(url, location.href);
      const host = parsed.hostname.replace(/^www\./, '');
      if (host === 'youtu.be') youtubeId = parsed.pathname.split('/')[1];
      else if (['youtube.com', 'm.youtube.com', 'youtube-nocookie.com'].includes(host)) {
        youtubeId = parsed.searchParams.get('v') || (/^\/(embed|shorts|live)\//.test(parsed.pathname) ? parsed.pathname.split('/')[2] : null);
      }
    } catch {}
    if (youtubeId && /^[\w-]{11}$/.test(youtubeId)) {
      $('video').hidden = true; $('video').removeAttribute('src'); $('video').load();
      $('youtube').src = 'https://www.youtube-nocookie.com/embed/' + youtubeId + '?rel=0';
      $('youtube').hidden = false; $('empty').hidden = true; $('setupNote').hidden = true;
      $('stageType').textContent = 'YOUTUBE'; $('status').textContent = 'READY TO PLAY';
      $('youtubeLink').href = 'https://www.youtube.com/watch?v=' + youtubeId;
      $('videoSource').hidden = false;
      return;
    }
    $('video').src = url;
    $('video').hidden = false; $('empty').hidden = true;
    $('setupNote').hidden = !local;
    $('stageType').textContent = local ? 'LOCAL PREVIEW' : 'PRESS PLAY';
    $('status').textContent = local ? 'PREVIEW · ONLY ON THIS DEVICE' : 'READY TO PLAY';
    if (config.posterUrl) $('video').poster = config.posterUrl;
  }
  function render() {
    $('demoTitle').textContent = config.title || 'The demo';
    $('demoDescription').textContent = config.description || '';
    document.title = (config.title || 'The demo') + ' — Demo room';
    if (config.videoUrl) showVideo(config.videoUrl);
    else {
      $('youtube').hidden = true; $('youtube').removeAttribute('src'); $('videoSource').hidden = true;
      $('video').pause(); $('video').removeAttribute('src'); $('video').load();
      $('video').hidden = true; $('empty').hidden = false; $('setupNote').hidden = false;
      $('status').textContent = 'READY WHEN YOU ARE'; $('stageType').textContent = 'YOUR FRONT-ROW SEAT';
    }
  }
  function loadFile(file) {
    if (!file || (!file.type.startsWith('video/') && !/\.(mp4|mov|webm|m4v)$/i.test(file.name))) {toast('Choose a video file such as MP4, MOV or WebM.');return;}
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(file); showVideo(objectUrl, true);
    toast('Preview loaded. Add the file to the site before sharing.');
  }
  $('pickVideo').addEventListener('click', () => $('fileInput').click());
  $('fileInput').addEventListener('change', e => loadFile(e.target.files[0]));
  ['dragenter', 'dragover'].forEach(type => $('stage').addEventListener(type, e => {e.preventDefault();$('stage').classList.add('dragging');}));
  $('stage').addEventListener('dragleave', e => {if (!$('stage').contains(e.relatedTarget)) $('stage').classList.remove('dragging');});
  $('stage').addEventListener('drop', e => {e.preventDefault();$('stage').classList.remove('dragging');loadFile(e.dataTransfer.files[0]);});
  $('editButton').addEventListener('click', () => {
    $('titleInput').value = config.title || ''; $('descriptionInput').value = config.description || ''; $('urlInput').value = config.videoUrl && /^https?:/.test(config.videoUrl) ? config.videoUrl : '';
    $('settings').showModal();
  });
  $('closeSettings').addEventListener('click', () => $('settings').close());
  $('settingsForm').addEventListener('submit', e => {
    e.preventDefault();
    const url = $('urlInput').value.trim();
    if (url && !/^https?:\/\//i.test(url)) {toast('Use a direct HTTPS or HTTP video URL.');return;}
    config = {...config, title: $('titleInput').value.trim() || 'The demo', description: $('descriptionInput').value.trim(), videoUrl: url || window.DEMO_CONFIG.videoUrl || ''};
    try {localStorage.setItem('demo-room-settings', JSON.stringify(config));} catch {}
    render(); $('settings').close(); toast('Changes saved in this browser.');
  });
  $('video').addEventListener('loadedmetadata', () => {
    const seconds = Math.floor($('video').duration);
    if (Number.isFinite(seconds)) $('stageType').textContent = Math.floor(seconds/60) + ':' + String(seconds%60).padStart(2,'0') + ' · DEMO RECORDING';
  });
  $('video').addEventListener('error', () => {
    $('video').hidden = true; $('empty').hidden = false; $('setupNote').hidden = false;
    $('status').textContent = 'VIDEO UNAVAILABLE'; $('emptyDescription').textContent = 'This video could not be played. Try an MP4 recording.';
    toast('Could not play the recording. Check the file or direct video URL.');
  });
  render();
})();
