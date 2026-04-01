# Ubuntu VM Deployment Guide

This guide assumes:

- Ubuntu VM
- Docker is already installed
- you want to run the bot in Docker
- you want the bot to restart automatically if the VM reboots

## 1. SSH into the VM

```bash
ssh YOUR_USER@YOUR_VM_IP
```

## 2. Install git if needed

```bash
sudo apt update
sudo apt install -y git
```

## 3. Clone the repo

```bash
git clone https://github.com/martintxortiz/valeron.git
cd valeron
```

## 4. Create the runtime folders

```bash
mkdir -p state
```

## 5. Create the `.env`

```bash
cat > .env <<'EOF'
key=PKCJ4GSM6NTRFZDRQW4OE2T3RJ
secret=2wkaeTq4GaiD8UFUVYHN4wdXmgsf5uhgyYsgm39VNKpv
APCA_PAPER=true
SYMBOL=BTC/USD
BAR_TIMEFRAME=15Min
RISK_PER_TRADE=0.01
MAX_ALLOC_PCT=0.95
POLL_SECONDS=60
LOG_LEVEL=INFO
DRY_RUN=true
STATE_PATH=state/runtime_state.json
HISTORY_LIMIT=500
POSITION_QTY_TOLERANCE=0.00000001
MIN_ORDER_NOTIONAL=10
MIN_STOP_DISTANCE_PCT=0.002
EOF
```

## 6. Build the Docker image

```bash
docker build -t valeron .
```

## 7. Run with Docker Compose

If `docker compose` is available:

```bash
docker compose up -d --build
```

Check status:

```bash
docker compose ps
```

Follow logs:

```bash
docker compose logs -f
```

Stop it:

```bash
docker compose down
```

## 8. Run with plain Docker

If you do not want to use Compose:

```bash
docker run -d \
  --name valeron \
  --restart unless-stopped \
  --env-file .env \
  -v "$(pwd)/state:/app/state" \
  valeron
```

Check status:

```bash
docker ps
```

Follow logs:

```bash
docker logs -f valeron
```

Stop it:

```bash
docker stop valeron
docker rm valeron
```

## 9. Verify Alpaca connection

After startup, logs should show something like:

- `event: "broker_state"`
- `account_id`
- `account_number`
- `account_status: "ACTIVE"`
- `crypto_status: "ACTIVE"`
- `equity`
- `cash`
- `buying_power`

If you see those, the bot is connected to Alpaca correctly.

## 10. Safe first launch

Keep this set at first:

```bash
DRY_RUN=true
APCA_PAPER=true
```

That means:

- it connects to Alpaca
- it computes signals
- it logs what it would do
- it does not place real orders

## 11. Switch from dry run to actual paper orders

Edit `.env`:

```bash
nano .env
```

Change:

```bash
DRY_RUN=false
```

Then restart:

With Compose:

```bash
docker compose up -d
```

With plain Docker:

```bash
docker stop valeron
docker rm valeron
docker run -d \
  --name valeron \
  --restart unless-stopped \
  --env-file .env \
  -v "$(pwd)/state:/app/state" \
  valeron
```

## 12. Update the bot later

```bash
cd ~/valeron
git pull
docker compose up -d --build
```

If you use plain Docker:

```bash
cd ~/valeron
git pull
docker build -t valeron .
docker stop valeron
docker rm valeron
docker run -d \
  --name valeron \
  --restart unless-stopped \
  --env-file .env \
  -v "$(pwd)/state:/app/state" \
  valeron
```

## 13. Troubleshooting

Check the configured remote:

```bash
git remote -v
```

It should point to:

```bash
https://github.com/martintxortiz/valeron.git
```

Check container logs:

```bash
docker logs -f valeron
```

Check saved runtime state:

```bash
cat state/runtime_state.json
```

Check the latest image:

```bash
docker images | grep valeron
```

## 14. Important note

Your `.env` contains credentials. Do not commit it, do not paste it into GitHub, and do not put it inside the Docker image.
