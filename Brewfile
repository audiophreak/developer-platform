# macOS workstation prerequisites for developer-platform.
#
# `devkit doctor` only CHECKS these (read-only). Installing is your decision:
#   brew bundle --file=Brewfile
#
# Node.js itself is deliberately not listed: each project pins it in .nvmrc, and a version
# manager (fnm below, or nvm / mise) selects it per project.
brew "git"
brew "gh"
brew "uv"
brew "python@3.14"
brew "fnm"

# Docker is deliberately not installed by this file, because the web-core profile and projects without a database do
# not need it. It IS required for local database work (`--set database=postgres` or `supabase`: `npm run db:*` and
# `npm run test:db`), for the web-core-template `db` tests, and for the native end-to-end scenario (`ios/scripts/e2e.mjs`).
# `devkit doctor` reports it as optional. Install Docker Desktop (or another Docker runtime) yourself when you need it:
# cask "docker-desktop"
