# Engineering Memory — Offline Industrial Deployment Guide

## 1. Overview
Engineering Memory is an on-premise industrial knowledge and diagnosis platform for heavy machinery (hydraulic excavators). The platform is architected to operate with **zero internet connection** during all normal technician diagnostic procedures.

### Architecture
```
Local Workstation / Server
├── React Frontend (Three.js / React Three Fiber / Recharts) [Port 3000]
├── FastAPI Backend (Python 3.13 / Pydantic / JWT) [Port 8000]
├── Local Database (MySQL 8.0 / SQLite Local Fallback) [Port 3306]
├── Vector Store (FAISS Flat IP Index, 1,015 vectors)
├── Local Embedder (BAAI/bge-small-en-v1.5)
├── Local Classifier (Random Forest hydraulic condition monitoring)
└── Local LLM Reasoning Engine (Qwen 3:4B through Ollama) [Port 11434]
```

---

## 2. Prerequisites
- **Operating System**: Windows 10/11 or Ubuntu Linux 20.04+
- **Python**: Python 3.10+ (Active: Python 3.13)
- **Node.js**: Node v18+ (Active: Node v22.19.0 with npm 11.6.0)
- **Ollama**: Local Ollama installed with `qwen3:4b`
- **RAM**: Minimum 8 GB (16 GB recommended for 3D + LLM)
- **GPU**: Optional (CPU inference supported out-of-the-box)

---

## 3. Step-by-Step Setup & Verification

### Step 1: Install Python Dependencies
```bash
python -m venv venv
.\venv\Scripts\pip install -r backend/requirements.txt
```

### Step 2: Set Up Database & Seed Initial Knowledge
```bash
.\venv\Scripts\python scripts/setup_database.py
```
This migrates:
- 3 Default Users (Admin, Engineer, Technician with PBKDF2 hashed passwords)
- 13 Industrial Excavator Components & 3D Mesh Mappings
- 25 Fleet Excavator Registry records
- 1,008 Grounded Historical Maintenance Cases

### Step 3: Ingest Engineering Manuals & Chunk Documentation
```bash
.\venv\Scripts\python scripts/ingest_documents.py
```
This chunks the industrial troubleshooting guide into overlapping semantic passages preserving document name, section heading, page number, and component.

### Step 4: Build FAISS Vector Memory
```bash
.\venv\Scripts\python scripts/build_faiss_index.py
```
Generates 384-dimensional normalized BGE embeddings for all 1,008 cases and 7 document chunks, saving the FAISS index to `models/engineering_memory.faiss` and permanent UUID mapping to `models/engineering_memory_mapping.json`.

### Step 5: Install & Build React Frontend
```bash
cd frontend
npm install
npm run build
```

### Step 6: Verify Ollama Local Engine
```bash
ollama list
```
Ensure `qwen3:4b` is listed. Test inference:
```bash
ollama run qwen3:4b "Respond with 'OFFLINE ENGINE OPERATIONAL'"
```

---

## 4. Launching the Platform

### Option A: One-Command Startup (Recommended)
Run the PowerShell startup script:
```powershell
.\scripts\startup.ps1
```
Or on Windows command prompt:
```cmd
.\scripts\startup.bat
```

### Option B: Manual Service Launch
**Terminal 1 (Backend API):**
```bash
.\venv\Scripts\python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 (React UI Workstation):**
```bash
cd frontend
npm run dev
```

Open browser at: `http://localhost:3000`

---

## 5. Offline Verification Procedure
1. Disconnect Ethernet cable and disable Wi-Fi on the workstation.
2. Navigate to `http://localhost:3000/diagnose`.
3. Select Machine `EXC-001`.
4. Enter symptoms:
   - "Slow boom movement"
   - "Weak digging force"
   - "Performance worsens when hot"
5. Click **ANALYZE MEMORY**.
6. Observe:
   - Evidence state is evaluated as **SUFFICIENT**.
   - Suspected component: **Hydraulic Pump** (`comp_pump`).
   - 3D Excavator model automatically centers, highlights, and pulses the Hydraulic Pump in warning red.
   - Grounded historical cases (CASE-001, etc.) and manual citations (Hydraulics Guide Page 1) are displayed.
   - Click **RECORD VERIFIED REPAIR** to test the technician knowledge preservation loop.
