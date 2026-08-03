# Instagram Growth Bot v4.0

Automation bot for Instagram growth — Follow, Scout, manual filtering, and Cleanup (Unfollow).
---

## System Requirements

| Requirement | Details |
|-------------|---------|
| **Kali Linux** | The environment this bot was built and tested on. Windows/macOS require adjustments (Chrome path, profile paths, etc.). |
| **Python 3.10+** | Python 3.11 recommended |
| **Google Chrome** | Installed at `/usr/bin/google-chrome` (version 148 in the current code) |
| **Instagram account** | Manual browser login on first run |

### Installing Chrome on Kali (if missing)

```bash
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update && sudo apt install -y google-chrome-stable
which google-chrome   # verify the path matches the code

How It Works — Overview

┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  CLI Menu   │ ──► │  Chrome (Selenium)│ ──► │  Instagram Web  │
└─────────────┘     └──────────────────┘     └─────────────────┘
       │                      │                        │
       ▼                      ▼                        ▼
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  SQLite DB  │ ◄── │  XPath + AI      │ ◄── │  Profiles /     │
│ users_status│     │  smart_find()    │     │  Suggestions    │
└─────────────┘     └──────────────────┘     └─────────────────┘

Recommended Project Structure:




---

## ⚠️ Disclaimer & Limitation of Liability
**READ THIS BEFORE USING THIS SOFTWARE.**
This project is provided **strictly for educational, research, and personal learning purposes only**.
By downloading, installing, or using this software, you acknowledge and agree that:
1. **Your responsibility** — You are solely responsible for how you use this tool. The author(s) and contributors assume **no liability** for any actions you take with it.
2. **Terms of Service** — Automating actions on Instagram (follow, unfollow, scraping, etc.) may violate [Instagram's Terms of Service](https://help.instagram.com/) and similar platform policies. Consequences may include account suspension, permanent ban, IP blocks, or legal action by the platform.
3. **Legal risk** — Depending on your jurisdiction, misuse of automation tools may violate laws related to unauthorized access, computer fraud, spam, data protection (e.g. GDPR), or platform abuse. **The author does not provide legal advice.** Consult a qualified attorney if you are unsure whether your use is lawful.
4. **No endorsement** — This software is **not** intended to harass, spam, impersonate, scrape private data at scale, or circumvent security measures for malicious purposes. Any such use is **expressly discouraged** and is **not supported**.
5. **No warranty** — The software is provided **"AS IS"**, without warranty of any kind, express or implied, including merchantability or fitness for a particular purpose. Use at your own risk.
6. **No support for misuse** — Issues arising from account bans, rate limits, legal notices, or criminal/civil proceedings related to misuse of this tool are **not the author's problem** and will not be addressed as bugs or support requests.
7. **Credentials & data** — You are responsible for securing your login credentials, API keys, and any data stored by this tool. Never commit secrets to version control.
**If you do not agree with these terms, do not use this software.**
---
*The author(s) disclaim all responsibility for direct, indirect, incidental, special, or consequential damages arising from the use or inability to use this software.*
