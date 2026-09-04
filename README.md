# Orion — Local AI Agent for Raspberry Pi 5

Orion is a fully local, terminal-based AI coding/ops agent that runs on a
Raspberry Pi 5. It talks to a local GGUF model via `llama-cpp-python`,
supports multi-step tool use (ReAct + native JSON tool calls), codebase RAG
search, MCP tool servers, and now **persistent storage** — files can be
saved either to the Pi's own local storage (SD card / SSD), Google Drive, or Microsoft OneDrive.

---

## Architecture

```
orion-llm/
├── .env                    # TAVILY_API_KEY, storage overrides, etc.
├── agent.py                 # OrionAgent — reasoning loop, tool dispatch, slash commands
├── chat.sh                  # launcher: activates venv, runs ui_cli.py
├── mcp_servers.json          # external MCP server config
├── requirements.txt
├── setup.sh                  # one-shot installer (venv + deps)
├── ui.py / ui_cli.py         # Rich-based terminal UI + main loop
├── docker/                   # optional containerized deployment
├── models/                   # local GGUF model files (e.g. Qwen2.5-0.5B)
├── storage/                    # ← ALL storage code + local file target lives here (sibling of tools/)
│   ├── __init__.py             # unified save_file / list_files / delete_file / cloud_status
│   ├── local_storage.py         # writes into this same storage/ folder (or SD card via env var)
│   └── cloud/
│       ├── gdrive_storage.py   # writes to Google Drive via rclone
│       └── onedrive_storage.py # writes to Microsoft OneDrive via rclone
└── tools/
    ├── __init__.py               # imports from the top-level storage/ package
    ├── registry.py                # unified tool registry (local + MCP + storage)
    ├── calculator.py
    ├── code_tools.py               # read/write/replace/list/search
    ├── dateTime.py
    ├── mcp_client.py                # stdio MCP client/manager
    ├── rag_engine.py                 # BM25 codebase RAG
    ├── search.py                      # Tavily web search
    └── storage/                    # storage tool bindings (gdrive, onedrive, local)
```

---

## Setup

```bash
git clone <your-repo> orion-llm
cd orion-llm
chmod +x setup.sh
./setup.sh              # creates venv, installs requirements.txt
```

Drop a `.env` file in the project root:
```
TAVILY_API_KEY=your_key_here
# Optional — see "Storage" section below
LOCAL_STORAGE_PATH=/mnt/cloudstore
GDRIVE_MOUNT_PATH=/mnt/gdrive
GDRIVE_REMOTE=gdrive:
ONEDRIVE_MOUNT_PATH=/mnt/onedrive
ONEDRIVE_REMOTE=onedrive:
```

Place a GGUF model in `models/` (default expected: `qwen2.5-0.5b-instruct-q4_k_m.gguf`),
then run:
```bash
./chat.sh
```

---

## Cloud & Local Storage

Orion can persist files to three backends, selected per-call with `target`:

| target     | Where it goes                                                   |
|------------|-------------------------------------------------------------------|
| `local`    | Directly inside `orion-llm/storage/` by default, or your mounted SD card/SSD if you set `LOCAL_STORAGE_PATH` (e.g. `/mnt/cloudstore`) |
| `gdrive`   | Your Google Drive, via the `rclone` mount at `/mnt/gdrive` (falls back to the `rclone` CLI if the mount isn't live) |
| `onedrive` | Your Microsoft OneDrive, via the `rclone` mount at `/mnt/onedrive` (falls back to the `rclone` CLI if the mount isn't live) |

All the storage code lives in the top-level `storage/` package — a
**sibling** of `tools/`, not nested inside it. `tools/registry.py` and
`tools/__init__.py` simply `from storage import ...` to use it.

### One-time Pi-side setup

1. **Local storage (SD card)** — format and mount the card, e.g.:
   ```bash
   sudo mkfs.ext4 /dev/mmcblk0p1
   sudo mkdir /mnt/cloudstore
   sudo mount /dev/mmcblk0p1 /mnt/cloudstore
   ```

2. **OneDrive Setup with `rclone`**:

   **Step A: Install rclone on Raspberry Pi 5**
   ```bash
   curl https://rclone.org/install.sh | sudo bash
   ```

   **Step B: Configure the `onedrive` remote**
   Run `rclone config` on the Pi SSH terminal:
   - Type `n` for **New remote**
   - Name: `onedrive`
   - Storage type: Choose `onedrive` (Microsoft OneDrive)
   - Client ID & Secret: Press Enter (leave blank)
   - Region: Choose `1` (OneDrive National / Global Cloud)
   - Edit advanced config: `n`
   - Use web browser to automatically authenticate: `n` (since Pi is headless over SSH)

   **Step C: Authorize on your PC**
   Install `rclone` on your Windows PC (or use an existing `rclone`), open PowerShell and run:
   ```powershell
   rclone authorize "onedrive"
   ```
   A browser window will open. Log into your Microsoft account and grant permissions. Copy the JSON token code printed in your PC's PowerShell terminal and paste it back into the Pi's `rclone config` prompt.

   Select drive type (usually `1` for OneDrive Personal/Business), confirm with `y`, and exit configuration (`q`).

   **Step D: Test access**
   ```bash
   rclone lsd onedrive:
   ```

   **Step E: Setup FUSE Mount & Persistent Service**
   Create mount directory and configure systemd:
   ```bash
   sudo mkdir -p /mnt/onedrive
   sudo chown rpi:rpi /mnt/onedrive
   ```
   Create `/etc/systemd/system/rclone-onedrive.service`:
   ```ini
   [Unit]
   Description=Rclone OneDrive Mount
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=rpi
   ExecStart=/usr/bin/rclone mount onedrive: /mnt/onedrive --vfs-cache-mode writes --allow-other
   ExecStop=/bin/fusermount -uz /mnt/onedrive
   Restart=on-failure
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```
   Enable and start the mount service:
   ```bash
   sudo sed -i 's/#user_allow_other/user_allow_other/' /etc/fuse.conf
   sudo systemctl daemon-reload
   sudo systemctl enable --now rclone-onedrive.service
   ```

### Using it from the agent

Slash commands (typed directly in the Orion chat):
```
/cloud                              # show local + Drive + OneDrive status and free space
/save report.pdf                    # save to local storage/ (default)
/save report.pdf gdrive              # save straight to Google Drive
/save report.pdf onedrive            # save straight to Microsoft OneDrive
```

Programmatic tools (callable by the LLM itself, or from Python):
```python
from tools import save_file, list_files, delete_file, cloud_status

save_file("output/result.csv", target="onedrive")
list_files(target="onedrive")
delete_file(target="onedrive", relative_path="old_report.pdf")
cloud_status()
```

The agent's system prompt instructs the model to call
`save_file_to_cloud`, `list_cloud_files`, and `cloud_storage_status` when a
user asks it to save, back up, or check on stored files.

---

## Other Commands

| Command                             | Description                                       |
|--------------------------------------|----------------------------------------------------|
| `/edit <file> [instruction]`         | Focus a file for editing, or apply an edit directly |
| `/rag <path>` / `/index`              | Index a directory for codebase search              |
| `/tools`                               | List all registered local + MCP tools               |
| `/mcp` / `/servers`                     | List active MCP servers                              |
| `/cloud` / `/storage`                    | Show local + Google Drive + OneDrive storage status   |
| `/save <file> [local\|gdrive\|onedrive]`| Save a file to local storage, Google Drive, or OneDrive|
| `/clear`                                  | Redraw the banner                                     |
| `exit` / `quit`                            | Quit Orion                                             |

---

## Testing

```bash
python3 test_all.py       # exercises tools, RAG, tool-call parsing, registry, and cloud storage
python3 test_search.py    # live Tavily API smoke test
```