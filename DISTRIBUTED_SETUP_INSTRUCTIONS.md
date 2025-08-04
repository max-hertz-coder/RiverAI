# 🏗️ Настройка распределенной архитектуры RiverAI

## 📋 Архитектура
- **Сервер 1**: Queue (RabbitMQ + Redis) + Worker
- **Сервер 2**: Bot

## 🚀 Быстрая настройка

### Сервер 1 (Queue + Worker)
```bash
# В корне проекта на Сервере 1:
chmod +x scripts/setup_server1.sh
./scripts/setup_server1.sh
```

### Сервер 2 (Bot)
```bash
# В корне проекта на Сервере 2:
chmod +x scripts/setup_server2.sh
./scripts/setup_server2.sh <IP_СЕРВЕРА_1>
# Пример: ./scripts/setup_server2.sh 176.123.160.130
```

## 📝 Ручная настройка

### Сервер 1 (Queue + Worker)

1. **Создайте Docker сеть:**
```bash
docker network create internal
```

2. **Настройте .env файл:**
```bash
# В .env файле на Сервере 1:
RABBITMQ_HOST=queue-rabbitmq
REDIS_HOST=queue-redis
```

3. **Запустите сервисы:**
```bash
# Queue сервисы
cd infrastructure/queue
docker-compose up -d

# Подождите 10 секунд
sleep 10

# Worker
cd ../worker
docker-compose up -d
```

4. **Проверьте IP адрес:**
```bash
# Запомните IP для Сервера 2
curl -s ifconfig.me
# или
hostname -I
```

### Сервер 2 (Bot)

1. **Настройте .env файл:**
```bash
# В .env файле на Сервере 2 замените IP на реальный адрес Сервера 1:
RABBITMQ_HOST=176.123.160.130  # IP Сервера 1
REDIS_HOST=176.123.160.130     # IP Сервера 1
```

2. **Проверьте доступность сервисов:**
```bash
# Проверьте RabbitMQ
telnet 176.123.160.130 5672

# Проверьте Redis
telnet 176.123.160.130 6379
```

3. **Запустите bot:**
```bash
cd infrastructure/bot
docker-compose up -d
```

## 🔧 Настройка Firewall

### На Сервере 1 откройте порты:
```bash
# UFW (Ubuntu)
sudo ufw allow 5672/tcp  # RabbitMQ
sudo ufw allow 6379/tcp  # Redis
sudo ufw allow 15672/tcp # RabbitMQ Management

# Или iptables
sudo iptables -A INPUT -p tcp --dport 5672 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 6379 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 15672 -j ACCEPT
```

## 🔍 Проверка работы

### На Сервере 1:
```bash
# Проверьте контейнеры
docker ps

# Проверьте логи worker
docker logs riverai-worker-1

# Проверьте RabbitMQ Management
# Откройте в браузере: http://IP_СЕРВЕРА_1:15672
```

### На Сервере 2:
```bash
# Проверьте контейнеры
docker ps

# Проверьте логи bot
docker logs bot-bot-1

# Проверьте подключения
telnet 176.123.160.130 5672
telnet 176.123.160.130 6379
```

## ❌ Устранение проблем

### Проблема: "Connection refused"
```bash
# На Сервере 1 проверьте:
docker ps | grep -E "(rabbitmq|redis)"
netstat -tlnp | grep -E ':(5672|6379)'

# На Сервере 2 проверьте:
telnet IP_СЕРВЕРА_1 5672
telnet IP_СЕРВЕРА_1 6379
```

### Проблема: "Network not found"
```bash
# На Сервере 1:
docker network create internal
docker-compose -f infrastructure/queue/docker-compose.yml up -d
```

### Проблема: Worker не получает задачи
```bash
# На Сервере 1 проверьте RabbitMQ:
docker exec queue-rabbitmq rabbitmqctl list_queues
docker exec queue-rabbitmq rabbitmqctl list_connections
```

## 📊 Мониторинг

### Проверка очередей:
```bash
# На Сервере 1
docker exec queue-rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged
```

### Проверка Redis:
```bash
# На Сервере 1
docker exec queue-redis redis-cli info keyspace
```

### Проверка логов:
```bash
# Worker
docker logs -f riverai-worker-1

# Bot
docker logs -f bot-bot-1

# Queue server
docker logs -f queue-server
``` 