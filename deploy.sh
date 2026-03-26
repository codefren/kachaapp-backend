#!/bin/bash

set -e

echo "🚀 DEPLOY INICIADO..."

cd ~/kachadigitalbcn/kachaapp-backend

echo "📥 Actualizando código..."
git pull origin main

echo "🐳 Reconstruyendo contenedores..."
docker compose -f docker-compose.production.yml up -d --build

echo "🗄 Aplicando migraciones..."
docker exec -i kachaapp-backend-django-1 python manage.py migrate --settings=config.settings.production

echo "📦 Recolectando estáticos..."
docker exec -i kachaapp-backend-django-1 python manage.py collectstatic --noinput --settings=config.settings.production

echo "📊 Estado de contenedores:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo "📜 Últimos logs Django:"
docker logs --tail 30 kachaapp-backend-django-1

echo "✅ DEPLOY COMPLETADO"
