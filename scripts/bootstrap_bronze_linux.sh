#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${VNSTOCK_API_KEY:-}" ]]; then
  echo "VNSTOCK_API_KEY is required"
  exit 2
fi

python -m pip install --upgrade pip
python -m pip install requests packaging vnstock vnai
python -m pip install --extra-index-url https://vnstocks.com/api/simple vnii vnstock_installer --force

curl -sL https://vnstocks.com/files/vnstock-cli-installer.run -o /tmp/vnstock-cli-installer.run
chmod +x /tmp/vnstock-cli-installer.run

/tmp/vnstock-cli-installer.run -- --non-interactive --api-key "$VNSTOCK_API_KEY" --language vi

python - <<'PY'
import vnstock_data
print("vnstock_data ready:", getattr(vnstock_data,"__version__","installed"))
PY
