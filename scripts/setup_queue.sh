#!/usr/bin/env bash
set -euo pipefail

# 1) Системные пакеты
apt update
apt install -y git python3 python3-venv python3-pip docker.io docker-compose openssh-client

# 2) Docker
systemctl enable docker
systemctl restart docker

# 3) SSH-ключ (приватник уже должен лежать в ~/.ssh/github-queue)
chmod 600 ~/.ssh/github-queue
# known_hosts для GitHub
ssh-keyscan -H github.com >> ~/.ssh/known_hosts

# 4) Клонирование и запуск
if [ ! -d /opt/ii-tutor-bot/.git ]; then
  git clone git@github.com:<ВАШ-LOGIN>/<ВАШ-РЕПО>.git /opt/ii-tutor-bot
fi

cd /opt/ii-tutor-bot

# Если в проекте есть requirements.txt:
if [ -f requirements.txt ]; then
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  deactivate
fi

docker-compose up -d --build
