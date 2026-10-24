# Tempo protected cloud receiver

Deployment-ready alternative to the blocked local-network and free-tunnel tests.
This package contains no API keys or health readings. It has not been deployed.

Deploy this directory as a Docker web service on a trusted hosting account with
HTTPS. Configure two different random secrets of at least 32 characters:

- `TEMPO_WRITE_KEY`: only allows submitting a heart-rate value.
- `TEMPO_READ_KEY`: only allows reading the latest value; keep it on the laptop.

The container uses one worker. A platform health check can use `/health`.
It retains only the latest reading in memory, exposes it for up to one hour,
and loses it on restart. This is an integration test, not production storage.

Open `https://YOUR_HOST/#key=YOUR_WRITE_KEY` on the iPhone. The browser stores the
write key in its tab session and removes it from the visible URL. Enter a recent
Apple Health value. Shortcuts setup is also available on that page: POST JSON to
`/watch` containing `heart_rate_bpm` and `access_key`.

To forward actual readings into the existing local Tempo server, set
`TEMPO_READ_KEY` in the receiving terminal and run:

```powershell
python forward_to_tempo.py --url https://YOUR_HOST
```

Both connections are outbound from the laptop; no inbound firewall rule or tunnel
is required. Keep the read key out of the phone, source repository, and logs.
Do not post screenshots or exports containing the keys publicly.

This receiver accepts user-submitted values. It does not independently verify
that a value originated from Apple Watch, provide a guaranteed sample frequency,
or align a full workout time series with a stroke video.


## Deploy this test receiver on Render

1. Sign up at https://dashboard.render.com/register (GitHub sign-in is convenient).
2. Open https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2FKang-Ji-2048%2FTempo%2Ftree%2Ftempo-watch-https-receiver
3. Review the Blueprint and keep the service on the **Free** plan. It defines only
   one web service and generates separate random read/write secrets automatically.
4. Create the service. Send Tempo the resulting HTTPS `.onrender.com` URL once it
   is Live. Do not post the generated secret values publicly.

The Free plan sleeps after 15 minutes without incoming traffic; its next request
can take about a minute to wake it. This test receiver loses its in-memory reading
on restart. Auto-deployment is disabled, so later changes to the source repository
will not silently redeploy this service.

Reference: https://render.com/docs/free
