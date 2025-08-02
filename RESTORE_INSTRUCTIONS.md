# 🔄 Восстановление конфигурации после изменений друга

## 🚨 Что было изменено неправильно:

1. **Создана неправильная сеть** `riverai-network` вместо `internal`
2. **Изменены имена контейнеров** в docker-compose файлах
3. **Нарушена распределенная архитектура** - все пытались объединить в один файл
4. **Неправильные зависимости** между сервисами

## 🚀 Быстрое восстановление

### На Сервере 1 (Queue + Worker):
```bash
chmod +x scripts/restore_config.sh
./scripts/restore_config.sh
```

### На Сервере 2 (Bot):
```bash
chmod +x scripts/restore_config.sh
./scripts/restore_config.sh
```

## 📝 Ручное восстановление

### Шаг 1: Остановить все контейнеры
```bash
# На обоих серверах
docker-compose -f infrastructure/queue/docker-compose.yml down
docker-compose -f infrastructure/worker/docker-compose.yml down
docker-compose -f infrastructure/bot/docker-compose.yml down
```

### Шаг 2: Удалить неправильную сеть
```bash
docker network rm riverai-network
```

### Шаг 3: Создать правильную сеть
```bash
docker network create internal
```

### Шаг 4: Удалить неправильные контейнеры
```bash
docker rm -f redis rabbitmq queue-server riverai-worker-1 2>/dev/null
```

### Шаг 5: Восстановить .env файлы

**На Сервере 1 (.env файл):**
```bash
# Замените в .env файле:
RABBITMQ_HOST=queue-rabbitmq
REDIS_HOST=queue-redis
```

**На Сервере 2 (.env файл):**
```bash
# Замените в .env файле IP на реальный адрес Сервера 1:
RABBITMQ_HOST=176.123.160.130  # IP Сервера 1
REDIS_HOST=176.123.160.130     # IP Сервера 1
```

### Шаг 6: Запустить сервисы

**На Сервере 1:**
```bash
# Queue сервисы
cd infrastructure/queue
docker-compose up -d

# Подождать 10 секунд
sleep 10

# Worker
cd ../worker
docker-compose up -d
```

**На Сервере 2:**
```bash
# Bot
cd infrastructure/bot
docker-compose up -d
```

## 🔍 Проверка восстановления

### Проверьте контейнеры:
```bash
docker ps
```

### Проверьте сеть:
```bash
docker network ls | grep internal
```

### Проверьте подключения (на Сервере 1):
```bash
docker exec riverai-worker-1 ping queue-rabbitmq
docker exec riverai-worker-1 ping queue-redis
```

### Проверьте логи:
```bash
# Worker
docker logs riverai-worker-1

# Bot
docker logs bot-bot-1

# Queue server
docker logs queue-server
```

## ❌ Если что-то пошло не так

### Полная очистка и перезапуск:
```bash
# Остановить все
docker stop $(docker ps -q)

# Удалить все контейнеры
docker rm $(docker ps -aq)

# Удалить все сети кроме default
docker network prune -f

# Создать сеть заново
docker network create internal

# Запустить по порядку (см. Шаг 6)
```

## 📋 Ожидаемый результат

После восстановления:
- ✅ Сеть `internal` создана
- ✅ Контейнеры `queue-redis`, `queue-rabbitmq`, `queue-server` запущены
- ✅ Контейнер `riverai-worker-1` подключен к сети
- ✅ Контейнер `bot-bot-1` подключается к внешним сервисам
- ✅ Нет ошибок "Connection refused"
- ✅ Нет ошибок "Network not found"

## 🔧 Дополнительные проверки

### Проверка RabbitMQ:
```bash
# На Сервере 1
docker exec queue-rabbitmq rabbitmqctl list_queues
```

### Проверка Redis:
```bash
# На Сервере 1
docker exec queue-redis redis-cli ping
```

### Проверка портов:
```bash
# На Сервере 1
netstat -tlnp | grep -E ':(5672|6379|15672)'
``` 