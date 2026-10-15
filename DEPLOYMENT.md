# Deployment en Servidor Privado con Docker Compose

Este documento explica cómo desplegar el proyecto completo en un servidor privado sin dependencias de tu portátil.

## Requisitos

- Docker >= 20.10
- Docker Compose >= 2.0
- 4GB RAM mínimo
- 20GB almacenamiento (para builds de APK)

## Instalación rápida

### 1. En tu servidor privado

```bash
# Clonar/copiar el proyecto
cd /opt
git clone <tu-repo> acces-remote
cd acces-remote

# Crear archivo .env con configuración
cp .env.production .env
# Edita .env y cambia:
# - POSTGRES_PASSWORD
# - SERVICE_KEY (genera una clave fuerte: `openssl rand -base64 32`)
# - PORTAL_BASE_URL (tu dominio)
```

### 2. Iniciar todos los servicios

```bash
docker-compose up -d
```

Esto inicia:
- **Redis 7** en puerto 6379 (cola de builds)
- **PostgreSQL 15** en puerto 5432 (base de datos)
- **Node.js server** en puerto 3000 (portal web + signaling)
- **Node.js worker** (procesa compilaciones de APK)

### 3. Verificar que está corriendo

```bash
docker-compose ps

# Debería mostrar:
# NAME                STATUS
# acces_redis_1       Up (healthy)
# acces_postgres_1    Up (healthy)
# acces_server_1      Up (healthy)
# acces_worker_1      Up
```

### 4. Ver logs

```bash
# Todos los servicios
docker-compose logs -f

# Solo el worker (para debuggear builds)
docker-compose logs -f worker

# Solo el server
docker-compose logs -f server
```

## Configuración para producción

### Nginx Reverse Proxy

Si quieres HTTPS y usar un dominio:

```nginx
server {
    listen 80;
    server_name tu-dominio.com;
    
    # Redirigir HTTP → HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name tu-dominio.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Para WebSocket
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Backups automáticos

Agregar a crontab:

```bash
# Backup diario a las 2am
0 2 * * * cd /opt/acces-remote && docker-compose exec -T postgres pg_dump -U acces acces > /backups/acces-$(date +\%Y\%m\%d).sql
```

## Flujo de uso

1. **Usuario técnico** → Abre portal en `https://tu-dominio.com`
2. **Crea cuenta** y genera APK para un cliente
3. **Worker procesa el build** (compila, firma, genera APK)
4. **Cliente instala APK** → Se conecta automáticamente al servidor
5. **Técnico controla desde cualquier lugar** vía portal web

## Troubleshooting

### Redis version error (como tenías ahora)
Con Docker, Redis viene con v7 (suficiente).

### Worker no procesa builds
```bash
docker-compose logs worker
# Ver qué error tiene
```

### Postgres connection error
```bash
# Verificar que postgres está corriendo
docker-compose exec postgres psql -U acces -d acces -c "SELECT 1"
```

### Limpiar todo y empezar de nuevo
```bash
docker-compose down -v
docker-compose up -d
```

## Escalabilidad futura

Si crece mucho:
- Múltiples workers en paralelo (agregar `docker-compose scale worker=3`)
- Separar Redis y Postgres en servidores distintos
- CDN para descargas de APK
- Load balancer si hay muchos hosts simultáneos

## Actualizar código

```bash
# Pull cambios
git pull origin main

# Reconstruir imágenes
docker-compose build

# Reiniciar servicios
docker-compose up -d
```

---

**¿Preguntas?** Revisa los logs: `docker-compose logs -f`
