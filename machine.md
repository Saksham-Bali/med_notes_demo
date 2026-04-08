# AGENT.md — Shared GPU System Operating Manual

## 0. Purpose

This document defines **strict operational rules and workflows** for using a shared high-performance compute system (CPU + GPU) safely, reproducibly, and without interfering with other users.

The agent must:

* Be **resource-aware**
* Maintain **isolation**
* Ensure **reproducibility**
* Avoid **system pollution**

---

## 1. System Overview

* Multi-core CPU (~100+ cores)
* RAM: ~120+ GB
* GPU: NVIDIA RTX A6000 (~48 GB VRAM)
* Shared among multiple users

---

## 2. Access

### SSH into system

```bash
ssh tyrone
```

No additional authentication logic required beyond configured access.

---

## 3. Session Management (MANDATORY)

All work MUST be done inside `tmux`.

### Create session

```bash
tmux new -s <session_name>
```

### Detach (leave running)

```
Ctrl + b, then d
```

### Reattach

```bash
tmux attach -t <session_name>
```

### List sessions

```bash
tmux ls
```

### Kill session (after completion)

```bash
tmux kill-session -t <session_name>
```

> Never run long processes outside tmux. SSH disconnections will kill them.

---

## 4. Directory Structure (STRICT)

All work must be project-scoped.

### Root workspace

```bash
~/projects/
```

### Create project

```bash
mkdir -p ~/projects/<project_name>
cd ~/projects/<project_name>
```

### Recommended structure

```
project_name/
├── env/                # local conda env
├── src/                # code
├── data/               # datasets (if allowed)
├── outputs/            # results
├── logs/               # logs
├── checkpoints/        # models
├── configs/            # experiment configs
└── AGENT.md            # this file
```

---

## 5. Environment Management (CRITICAL POLICY)

🚫 DO NOT install environments globally or in home directory.

### ❌ Forbidden

```bash
conda create -n myenv python=3.10
```

### ✅ Required (project-local env)

```bash
conda create --prefix ./env python=3.10
```

Activate:

```bash
conda activate ./env
```

Verify:

```bash
which python
```

Expected output:

```
.../project_name/env/bin/python
```

---

## 6. Dependency Installation

Inside project directory ONLY:

```bash
pip install -r requirements.txt
```

or manually:

```bash
pip install torch torchvision transformers datasets
```

### Freeze dependencies

```bash
pip freeze > requirements.txt
```

---

## 7. Resource Awareness Protocol (MANDATORY BEFORE RUNNING)

### 7.1 Check GPU

```bash
nvidia-smi
```

Interpretation:

* `GPU-Util = 0%` → free
* `Memory < 1GB` → only display processes
* Any `python` using GPU → GPU occupied

---

### 7.2 Check CPU

```bash
htop
```

Look for:

* High CPU processes
* Multiple cores active

---

### 7.3 Check active user processes

```bash
ps aux | grep python
```

---

### 7.4 Decision Rule

| Condition             | Action              |
| --------------------- | ------------------- |
| GPU idle              | Proceed             |
| GPU busy              | Wait                |
| Unsure                | Investigate further |
| Another user training | Do NOT interrupt    |

---

## 8. Job Execution

### Standard run

```bash
python src/train.py
```

---

### Background execution (recommended for long jobs)

```bash
nohup python src/train.py > logs/output.log 2>&1 &
```

---

### With explicit logging

```bash
python src/train.py > logs/run_$(date +%F_%T).log 2>&1
```

---

## 9. Logging and Reproducibility (REQUIRED)

Each run must:

* Save logs
* Save config
* Save checkpoints

### Example

```bash
mkdir -p logs outputs checkpoints configs
```

Save config:

```bash
cp config.yaml configs/run_1.yaml
```

---

## 10. GPU Usage Discipline

### Before using GPU:

* Confirm idle state
* Confirm no large VRAM usage
* Confirm no active training

### While using GPU:

* Monitor periodically

```bash
watch -n 1 nvidia-smi
```

---

## 11. Process Monitoring

### Find your processes

```bash
ps -u $USER
```

### Find specific job

```bash
pgrep -af python
```

---

## 12. Termination Protocol

### Graceful stop

```bash
kill <PID>
```

### Force kill (last resort)

```bash
kill -9 <PID>
```

---

## 13. Data Handling

* Keep datasets inside project if small
* Use shared storage only if required
* Do NOT duplicate large datasets unnecessarily

---

## 14. Cleanup Rules

After finishing:

* Kill all jobs
* Remove temp files
* Archive results if needed

```bash
rm -rf tmp/
```

---

## 15. Prohibited Actions

* ❌ Global conda installs
* ❌ Running without tmux
* ❌ Killing others' processes
* ❌ Using GPU without checking
* ❌ Writing outside project scope
* ❌ Leaving zombie processes

---

## 16. Minimal End-to-End Workflow

```bash
ssh tyrone

tmux new -s exp1

mkdi
```

