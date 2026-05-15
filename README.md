# standup-gen

Generates a summary from a git repository's commit history. Optionally uses AI (via Groq) to turn the raw commits into a short, readable paragraph you can copy and send.

## Setup

1. Install [uv](https://docs.astral.sh/uv/) if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Clone the repo and install `standup` as a global command:

```bash
git clone https://github.com/nicoleman0/standup-gen.git
cd standup-gen
uv tool install .
```

3. Add `uv`'s tool bin to your PATH (only needed once):

```bash
uv tool update-shell
```

Restart your terminal or `source ~/.zshrc` — after that, `standup` will be available anywhere.

4. Set your Groq API key permanently (only needed for `--summarize`):

**zsh** (`~/.zshrc`):
```zsh
echo 'export GROQ_API_KEY=your_key_here' >> ~/.zshrc
source ~/.zshrc
```

**bash** (`~/.bashrc`):
```bash
echo 'export GROQ_API_KEY=your_key_here' >> ~/.bashrc
source ~/.bashrc
```

Alternatively, you can create a `.env` file in the repo root instead:

```
GROQ_API_KEY=your_key_here
```

## Usage

```bash
standup /path/to/your/repo --since 1.day.ago --summarize
```

**Arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `repo_path` | *(required)* | Path to the git repository |
| `--since` | `7.days.ago` | How far back to look |
| `--until` | `now` | End of the range |
| `--author` | *(none)* | Filter to a specific author |
| `--summarize` | off | Use AI to write a prose summary |
| `--output` | *(stdout)* | Write output to a file instead |
