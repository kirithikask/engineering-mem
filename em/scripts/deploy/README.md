# Deploy Engineering Memory — Oracle Cloud "Always Free"

This gets you a **permanent public URL** (`http://<vm-ip>:8000`) that works from any
network, with the full app: React UI + FastAPI + Qwen 3:4B + BGE + FAISS + database —
**100% free forever** (Oracle's Always Free tier, no expiry, no billing while you
stay inside the free limits).

## What you get

| | |
|---|---|
| URL | `http://<vm-public-ip>:8000` — fixed forever, works from any WiFi/country |
| Machine | Ampere A1 ARM VM: 4 cores, **24 GB RAM**, 200 GB disk (Always Free) |
| Runs | Everything: model, database, index — nothing else needed |
| Persists | Yes — reboots auto-restart the app (systemd); data survives |
| Cost | ₹0 / $0 while within Always Free limits |

## Part A — One-time, in your browser (~30 min)

1. **Create the account** → https://www.oracle.com/cloud/free/
   Needs email + a card for verification (₹0 charged; card is never used unless you
   manually upgrade). Choose **Home region = closest to you** — Always Free resources
   must live in your home region. ⚠️ Registration can take a few minutes to verify.
2. **Create the VM** — Console (top-left ☰) → **Compute → Instances → Create Instance**:
   - Name: `engineering-memory`
   - Image: **Ubuntu 22.04** (or 24.04)
   - Shape: **Ampere** → `VM.Standard.A1.Flex` → **4 OCPU, 24 GB** (the full free allowance)
   - Boot volume: default (or bump to 100 GB, still free)
   - Networking: leave defaults (public IP assigned)
   - SSH keys: **"Generate a key pair"** → download **BOTH** the private key (`.key`)
     and public key — save the private key somewhere safe (you cannot recover it)
   - Click **Create** → note the **Public IP address** on the instance page
3. **Open port 8000** — while the VM boots:
   Instance page → click the **Subnet** link → **Security List** → **Add Ingress Rule**:
   - Source CIDR: `0.0.0.0/0`, Protocol: `TCP`, Destination Port: `8000` → **Add Rule**

## Part B — I prepare the bundle, you upload it (~10 min)

1. On your PC, build the bundle (or I run this for you):
   ```bash
   cd /d/emm/em
   tar czf ../em_bundle.tar.gz --exclude venv --exclude node_modules --exclude .git .
   ```
2. **Upload from your browser** (no SCP needed): Cloud Shell (the `>_` icon in the
   Oracle console) has a **File → Upload** menu. Upload `D:\emm\em_bundle.tar.gz` there.

## Part C — On the VM: two commands

In Cloud Shell (upload lands in your home dir), the VM is one SSH away:

```bash
ssh -i <your-private-key>.key ubuntu@<VM_PUBLIC_IP>
```

then, inside the VM:

```bash
# 1. receive the bundle from Cloud Shell (run in Cloud Shell, NOT the VM):
#    scp -i <key> ~/em_bundle.tar.gz ubuntu@<VM_PUBLIC_IP>:~/

# 2. extract and provision:
tar xzf em_bundle.tar.gz -C em_bundle
sudo bash em_bundle/scripts/deploy/oracle_setup.sh
```

The script installs Ollama + qwen3:4b, the Python stack, registers a systemd service
(auto-start on boot, restart on crash), opens the VM firewall, and health-checks.
It finishes by printing your permanent URL:

```
http://<VM_PUBLIC_IP>:8000
```

## Verify

- `http://<VM_PUBLIC_IP>:8000` → login page (accounts from `scripts/setup_database.py`)
- `http://<VM_PUBLIC_IP>:8000/api/health` → `"status": "online"`, `qwen_ollama: true`
- Run a diagnosis — retrieval in milliseconds; reasoning a bit slower than your PC
  (CPU-only ARM, ~1–2 min for the full pass, evidence renders first)

## Daily operation

| Task | Command (on the VM) |
|---|---|
| Status | `systemctl status engineering-memory` |
| Logs | `journalctl -u engineering-memory -f` |
| Restart | `sudo systemctl restart engineering-memory` |
| Rebuild index after data change | `venv/bin/python scripts/build_faiss_index.py` then restart |

## Common issues

| Symptom | Fix |
|---|---|
| Browser timeout on the URL | Ingress rule for 8000 missing (Part A step 3) |
| Health says `qwen_ollama: false` | `ollama list` on the VM — pull again if empty |
| "Out of memory" in logs | Confirm shape is 24 GB: `free -h` |
| Forgot SSH key | Destroy + recreate instance (free tier, nothing lost but setup) |

## Honest tradeoffs vs your current setup

- Reasoning is CPU-bound on ARM — expect **~60–120 s** per full reasoning pass
  (your PC did ~80 s; same order). Evidence still renders in <1 s first.
- Your home internet is no longer required — the app lives in Oracle's datacenter.
- The single weak point remains document evidence depth (7 manual chunks), not hosting.
