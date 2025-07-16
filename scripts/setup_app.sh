#!/usr/bin/env bash
set -euo pipefail

# 1) Установка необходимых пакетов (при первом запуске)
if [ ! -d /opt/RiverAI/.git ]; then
    apt update && apt install -y git python3 python3-venv python3-pip docker.io docker-compose-plugin openssh-client
    systemctl enable docker
    systemctl restart docker
fi

# 2) Настройка SSH-доступа к репозиторию
mkdir -p ~/.ssh
chmod 600 ~/.ssh/github-app
grep -q github.com ~/.ssh/known_hosts || ssh-keyscan -H github.com >> ~/.ssh/known_hosts

# 3) Клонирование и обновление репозитория
if [ ! -d /opt/RiverAI/.git ]; then
    git clone git@github.com:max-hertz-coder/RiverAI.git /opt/RiverAI
fi
cd /opt/RiverAI
git pull origin main || { git fetch origin main && git reset --hard origin/main && git clean -fd; }

# 4) Настройка .env
if [ -f .env.example ] && [ ! -f .env ]; then
    cp .env.example .env
    echo "WARN: .env created from example, please update it with actual secrets" >&2
fi

# 5) Запуск/перезапуск контейнеров приложения
docker compose up -d --build --remove-orphans

# 6) Логирование
echo "$(date +'%F %T') Deploy script finished on APP server" >> /opt/RiverAI/deploy.log
