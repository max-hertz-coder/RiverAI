#!/usr/bin/env bash
set -euo pipefail

# 1) Установка необходимых пакетов (выполняется при первом запуске)
if [ ! -d /opt/RiverAI/.git ]; then
    apt update && apt install -y git python3 python3-venv python3-pip docker.io docker-compose-plugin openssh-client
    systemctl enable docker
    systemctl restart docker
fi

# 2) Настройка SSH-ключа для доступа к репозиторию
mkdir -p ~/.ssh
chmod 600 ~/.ssh/github-queue
# Добавляем GitHub в known_hosts (если не добавлен ранее)
grep -q github.com ~/.ssh/known_hosts || ssh-keyscan -H github.com >> ~/.ssh/known_hosts

# 3) Клонирование репозитория (если не склонирован) и обновление кода
if [ ! -d /opt/RiverAI/.git ]; then
    git clone git@github.com:max-hertz-coder/RiverAI.git /opt/RiverAI
fi
cd /opt/RiverAI
git pull origin main || { git fetch origin main && git reset --hard origin/main && git clean -fd; }

# 4) Настройка переменных окружения (.env)
if [ -f .env.example ] && [ ! -f .env ]; then
    cp .env.example .env
    echo "WARN: .env created from example, please update secrets" >&2
fi
# Копируем .env в папку queue, чтобы docker-compose мог её видеть
cp -f .env queue/.env

# 5) Запуск (или обновление) контейнеров очереди
cd queue
docker compose up -d --build --remove-orphans

# 6) Логирование результата деплоя
echo "$(date +'%F %T') Deploy script finished on QUEUE server" >> /opt/RiverAI/deploy.log
