# Local dev convenience script
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Copying .env.example -> .env"
    echo "    Edit .env and set TELEGRAM_BOT_TOKEN before running again."
    cp .env.example .env
    exit 1
fi

# Make sure deps are installed
if ! python -c "import aiogram" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

echo "🚀 Starting IVASMS OTP Bot..."
exec python -m bot.main
