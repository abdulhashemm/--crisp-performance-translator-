# How to Set Up This Project on GitHub

## Step-by-step guide (no prior Git experience needed)

---

## Option A: Using GitHub Desktop (Easiest — No Terminal)

### 1. Install GitHub Desktop

- Go to [https://desktop.github.com/](https://desktop.github.com/)
- Download and install
- Sign in with your GitHub account (create one at github.com if needed)

### 2. Create a new repository

- Open GitHub Desktop
- Click **File > New Repository**
- Name: `crisp-performance-translator`
- Description: "Command-center risk monitoring system for CMH7 outbound operations"
- Local path: choose your Desktop or Documents folder
- Check "Initialize with a README" = NO (we already have one)
- Click **Create Repository**

### 3. Copy your project files into the repo folder

- GitHub Desktop will show you the folder location (click "Show in Explorer")
- Copy ALL your project files into that folder:- README.md
- requirements.txt
- crisp_translator.py
- data_connector.py
- dashboard.py
- shift_report.py
- sample_crisp_export.csv
- .gitignore
- docs/proposal.pptx (create a docs/ folder first)

### 4. Commit and push

- Go back to GitHub Desktop
- You'll see all files listed as "changes"
- In the bottom-left, type a commit message: "Initial commit - CRISP Performance Translator v0.1"
- Click **Commit to main**
- Click **Publish repository** (top bar)
- Choose: Private (recommended for now)
- Click **Publish**

### Done! Your code is now on GitHub.

---

## Option B: Using Terminal / Command Line

### 1. Install Git

- Windows: Download from [https://git-scm.com/download/win](https://git-scm.com/download/win)
- After install, open "Git Bash" from Start Menu

### 2. Configure Git (one-time setup)

```bash
git config --global user.name "Abdulrahman Hashem"
git config --global user.email "aqhashem@amazon.com"

```

### 3. Create the repo on GitHub

- Go to [https://github.com/new](https://github.com/new)
- Repository name: `crisp-performance-translator`
- Description: "Command-center risk monitoring system for CMH7 outbound operations"
- Private (recommended)
- DON'T initialize with README (we have our own)
- Click **Create repository**

### 4. Push your code

```bash
# Navigate to your project folder
cd ~/Desktop/crisp-performance-translator

# Initialize git
git init

# Add all files
git add .

# First commit
git commit -m "Initial commit - CRISP Performance Translator v0.1"

# Connect to GitHub (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/crisp-performance-translator.git

# Push
git branch -M main
git push -u origin main

```

### 5. Verify

- Go to [https://github.com/YOUR_USERNAME/crisp-performance-translator](https://github.com/YOUR_USERNAME/crisp-performance-translator)
- You should see all your files with the README displayed

---

## After Setup: Daily Workflow

When you make changes:

**GitHub Desktop:**

1. Make your changes to files
2. Open GitHub Desktop — it auto-detects changes
3. Type a commit message (e.g., "Added real CRISP data ingestion")
4. Click Commit, then Push

**Terminal:**

```bash
git add .
git commit -m "Added real CRISP data ingestion"
git push

```

---

## Recommended Commit Messages for Your Project

Use clear messages that tell a story:

- "Initial commit - CRISP Performance Translator v0.1"
- "Add severity scoring engine with escalation logic"
- "Add data connector for CRISP CSV/Excel imports"
- "Add Streamlit dashboard with NOC-style theme"
- "Add shift handoff report generator"
- "Plug in real CRISP data from CMH7"
- "Tune severity thresholds based on floor validation"
- "Add trend analytics for multi-day patterns"

---

## Tips

- **Keep it private** until your project is validated with leadership
- **Don't commit real CRISP data** — the .gitignore blocks .xlsx files
- **Commit often** — every meaningful change gets its own commit
- **Write good commit messages** — they tell the story of your project
- **Pin the repo** on your GitHub profile once it's polished

---

## Your Final Repo Structure

```
crisp-performance-translator/
├── .gitignore
├── README.md
├── requirements.txt
├── crisp_translator.py
├── data_connector.py
├── dashboard.py
├── shift_report.py
├── sample_crisp_export.csv
└── docs/
    └── CRISP_Performance_Translator.pptx

```

