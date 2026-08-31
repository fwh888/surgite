Review the current codebase and update AGENTS.md to accurately reflect the current state of the project.

Steps:
1. Read the current AGENTS.md
2. Explore the project structure: list all files, read key source files in `surgite/`, `docs/`, and config files (`pyproject.toml`, `docker-compose.yml`, etc.)
3. Check git log for recent changes since the AGENTS.md was last updated
4. Compare what AGENTS.md says against what the code actually does today — look for:
   - Outdated architecture descriptions or data flow diagrams
   - Missing or removed modules/files
   - New environment variables not listed
   - Commands that no longer work or new ones that are missing
   - "Planned" items that have since been implemented
   - Known issues that have been fixed
5. Edit AGENTS.md in place with accurate, up-to-date content. Preserve the existing structure and tone — only change what's wrong or missing. Do not add sections that aren't warranted by actual code.
