# SysManage server Homebrew cask — Phase 11.8 server-side stub.
#
# Cask form rather than formula because the server is a multi-component
# install (Python service + nginx + postgres) and the release workflow
# already produces a native macOS .pkg installer (see
# build-and-release.yml -> installer/dist/sysmanage-*-macos.pkg).
# Wrapping the .pkg as a cask reuses the same artifact users would
# download manually.
#
# Lives in the sysmanage repo *pending* the user creating the
# ``bceverly/homebrew-tap`` GitHub repository.  Once the tap exists,
# copy this file to:
#     <tap-root>/Casks/sysmanage.rb
# and ``brew install --cask bceverly/tap/sysmanage`` Just Works for
# every macOS client globally.
#
# *** USER ACTION REQUIRED ***
#
# Per-release update workflow (until a sysmanage-side
# ``homebrew-tap`` job lands in build-and-release.yml mirroring the
# agent's DRY-RUN-only stub):
#
#   1. Bump ``version`` to match the release tag.
#   2. Re-compute ``sha256`` against the macOS .pkg:
#         shasum -a 256 sysmanage-X.Y.Z-macos.pkg
#   3. ``cd ~/path/to/homebrew-tap``
#      ``cp <here>/sysmanage.rb Casks/sysmanage.rb``
#      ``git commit -am "sysmanage X.Y.Z"``
#      ``git push``
#   4. End users get upgrades via ``brew upgrade --cask sysmanage``.
#
# Single tap repo (``bceverly/homebrew-tap``) hosts BOTH formulas /
# casks:
#     Formula/sysmanage-agent.rb   (agent — Python venv formula)
#     Casks/sysmanage.rb           (this file — server .pkg cask)
#
# Home-lab / dev usage:  Mac users can stand up a local SysManage
# server with ``brew install --cask bceverly/tap/sysmanage`` for
# evaluation before production deployment to Linux.

cask "sysmanage" do
  version "0.0.0"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"

  url "https://github.com/bceverly/sysmanage/releases/download/v#{version}/sysmanage-#{version}-macos.pkg"
  name "SysManage"
  desc "Open-source endpoint management platform (server)"
  homepage "https://github.com/bceverly/sysmanage"

  pkg "sysmanage-#{version}-macos.pkg"

  uninstall pkgutil: "org.sysmanage.server"

  # Leave /etc/sysmanage.yaml + /var/lib/sysmanage alone on uninstall
  # by default; ``brew uninstall --cask --zap sysmanage`` opts in to
  # wiping user data.
  zap trash: [
    "~/Library/Application Support/SysManage",
    "~/Library/Logs/SysManage",
    "/etc/sysmanage.yaml",
    "/var/lib/sysmanage",
    "/var/log/sysmanage",
  ]
end
