# 🔧 Инструкция по исправлению конфигурации на сервере

## Проблемы, которые нужно исправить:

1. **Неправильные хосты в .env файле** - указаны внешние IP вместо имен контейнеров
2. **Проблемы с Docker сетями** - контейнеры не могут найти друг друга
3. **Порядок запуска сервисов** - нужно запускать в правильной последовательности

## 🚀 Автоматическое исправление (рекомендуется)

```bash
# На сервере в корне проекта RiverAI выполните:
chmod +x scripts/fix_server_config.sh
./scripts/fix_server_config.sh
```

## 📝 Ручное исправление

### 1. Создайте Docker сеть
```bash
docker network create internal
```

### 2. Исправьте .env файл
Найдите ваш .env файл на сервере и замените эти строки:

**БЫЛО:**
```bash
RABBITMQ_HOST=176.123.160.130
REDIS_HOST=176.123.160.130
```

**СТАЛО:**
```bash
RABBITMQ_HOST=queue-rabbitmq
REDIS_HOST=queue-redis
```

### 3. Остановите все контейнеры
```bash
cd infrastructure/queue && docker-compose down
cd ../worker && docker-compose down  
cd ../bot && docker-compose down
```

### 4. Запустите в правильном порядке

```bash
# 1. Сначала queue (создаст сеть internal)
cd infrastructure/queue
docker-compose up -d

# 2. Подождите 10 секунд
sleep 10

# 3. Затем worker
cd ../worker
docker-compose up -d

# 4. Подождите 5 секунд
sleep 5

# 5. Наконец bot
cd ../bot
docker-compose up -d
```

## 🔍 Проверка исправления

### Проверьте статус контейнеров:
```bash
docker ps
```

### Проверьте сеть:
```bash
docker network ls | grep internal
```

### Проверьте подключения между контейнерами:
```bash
docker exec riverai-worker-1 ping queue-rabbitmq
docker exec riverai-worker-1 ping queue-redis
```

### Проверьте логи:
```bash
docker logs riverai-worker-1
docker logs bot-bot-1
```

## ❌ Если что-то пошло не так

### Удалите все и начните заново:
```bash
# Остановить все
docker-compose -f infrastructure/queue/docker-compose.yml down
docker-compose -f infrastructure/worker/docker-compose.yml down
docker-compose -f infrastructure/bot/docker-compose.yml down

# Удалить сеть
docker network rm internal

# Создать сеть заново
docker network create internal

# Запустить по порядку (см. шаг 4 выше)
```

## 📋 Ожидаемый результат

После исправления в логах должно быть:
- ✅ Нет ошибок "Connect call failed"
- ✅ Нет ошибок "network not found"
- ✅ Контейнеры успешно подключаются друг к другу
- ✅ Worker получает задачи из RabbitMQ
- ✅ Bot отправляет сообщения пользователям 