# Tempo watch HTTPS receiver deployment

This branch adds an isolated, temporary Apple Health heart-rate receiver.
It does not contain the uncommitted Android/backend integration work on the local
main checkout. See [watch_receiver/README.md](watch_receiver/README.md).

[Deploy the Free receiver on Render](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2FKang-Ji-2048%2FTempo%2Ftree%2Ftempo-watch-https-receiver)

The Blueprint creates one Free web service, generates separate read/write keys,
and disables automatic redeploys. There are no committed keys or health readings.
