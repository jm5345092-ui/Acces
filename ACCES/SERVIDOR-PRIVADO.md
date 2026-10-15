# 🚀 Deployment en Servidor Privado - Guía Completa

## Estado Actual

✅ Todo está configurado para deployar en un servidor privado  
✅ Redis 7 (versión correcta) incluida en Docker  
✅ PostgreSQL configurada  
✅ Worker.js listo para compilar APKs  
✅ Sistema de backups automáticos  

## Requisitos del Servidor

- **OS**: Ubuntu 20.04+ / Debian 11+ / CentOS 7+ (o Windows Server con WSL2)
- **CPU**: 2 cores mínimo (4 recomendado)
- **RAM**: 4GB mínimo (8GB recomendado)
- **Disco**: 50GB (para builds de APK y backups)
- **Docker**: v20.10+
- **Docker Compose**: v2.0+

## Instalación en 5 minutos

### 1️⃣ En tu servidor, copia el proyecto

```bash
cd /opt
git clone https://github.com/tu-usuario/acces.git
cd acces
```

### 2️⃣ Ejecuta el script de setup

```bash
bash setup-server.sh
```

El script automáticamente:
- ✓ Verifica Docker y Docker Compose
- ✓ Genera claves secretas seguras
- ✓ Crea archivo .env
- ✓ Descarga imágenes Docker
- ✓ Compila imágenes locales
- ✓ Inicia todos los servicios
- ✓ Configura backups automáticos

### 3️⃣ Edita la configuración

```bash
nano .env
```

Cambia:
```
PORTAL_BASE_URL=https://tu-dominio.com  # ← Cambiar por tu dominio/IP
POSTGRES_PASSWORD=...                     # ← Ya generado, opcional cambiar
SERVICE_KEY=...                           # ← Ya generado, mantener seguro
```

### 4️⃣ Verifica que está corriendo

```bash
docker-compose ps

# Deberías ver:
# NAME                 STATUS
# acces-redis-1        Up (healthy)
# acces-postgres-1     Up (healthy)
# acces-server-1       Up (healthy)
# acces-worker-1       Up
```

### 5️⃣ Abre el portal

```
http://tu-servidor:3000
```

O si configuraste Nginx con HTTPS:
```
https://tu-dominio.com
```

---

## Configuración Recomendada para Producción

### 🔒 SSL/HTTPS con Let's Encrypt

```bash
# Instala certbot
sudo apt install certbot python3-certbot-nginx

# Obtén certificado (reemplaza tu-dominio.com)
sudo certbot certonly --standalone -d tu-dominio.com

# Los certificados quedarán en:
# /etc/letsencrypt/live/tu-dominio.com/
```

Luego edita `nginx.conf` y actualiza las rutas de SSL.

### 🏗️ Nginx Reverse Proxy

1. Instala Nginx:
```bash
sudo apt install nginx
```

2. Copia configuración:
```bash
sudo cp nginx/nginx.conf /etc/nginx/sites-available/acces
sudo ln -s /etc/nginx/sites-available/acces /etc/nginx/sites-enabled/
sudo nginx -t  # Verifica sintaxis
sudo systemctl restart nginx
```

### 💾 Backups Automáticos

Agregar a crontab para backup diario:

```bash
# Abre crontab
crontab -e

# Agrega esta línea (backup a las 2 AM):
0 2 * * * cd /opt/acces && ./scripts/backup.sh >> /var/log/acces-backup.log 2>&1
```

Verifica que funciona:
```bash
./scripts/backup.sh
ls -lh ./backups/
```

### 📊 Monitoreo

Ver logs en tiempo real:
```bash
# Todo
docker-compose logs -f

# Solo worker (compilaciones)
docker-compose logs -f worker

# Solo servidor
docker-compose logs -f server

# Solo base de datos
docker-compose logs -f postgres
```

---

## Flujo de Uso Completo

### Para el Técnico (Usuario)

1. **Accede al portal**: https://tu-dominio.com
2. **Crea una cuenta**: username + password
3. **Genera APK para un cliente**:
   - Ve a "Conectar"
   - Sube ícono de la app
   - Ingresa nombre y URL (opcional)
   - Haz clic en "Generar APK"
4. **Worker compila automáticamente** (2-5 minutos)
5. **Descarga el APK**: Link en la lista de builds

### Para el Cliente Remoto (Host)

1. **Recibe el APK personalizado**
2. **Instala en su teléfono**
3. **Abre la app y otorga permiso de accesibilidad**
4. **Automáticamente conecta al servidor**
5. **El técnico lo controla desde el portal**

---

## Solución de Problemas

### Redis version error
```
Error: Redis version needs to be greater or equal than 5.0.0
```
**Causa**: Docker Compose trae Redis 7, no debería pasar  
**Solución**: `docker-compose down -v && docker-compose up -d`

### Worker no procesa builds
```bash
docker-compose logs worker
# Ver qué error tiene
```

### PostgreSQL connection error
```bash
docker-compose exec postgres psql -U acces -d acces -c "SELECT 1"
```

### Espacio en disco lleno
```bash
# Ver tamaño de builds
du -sh ./portal/builds/

# Limpiar builds antiguos
find ./portal/builds -type f -mtime +30 -delete
```

---

## Actualizar Código

```bash
# Pull cambios del repo
git pull origin main

# Reconstruir imágenes
docker-compose build

# Reiniciar
docker-compose up -d
```

---

## Escalabilidad Futura

Si crece y necesitas más performance:

```yaml
# docker-compose.yml - agregar múltiples workers
services:
  worker:
    deploy:
      replicas: 3  # 3 compiladores en paralelo
```

O separar en múltiples servidores:
- Server #1: Portal + Signaling (Node.js)
- Server #2: Base de datos (PostgreSQL)
- Server #3: Cache (Redis)
- Server #4+: Workers (compiladores APK)

---

## Checklist Pre-Producción

- [ ] Cambié PORTAL_BASE_URL en .env
- [ ] Configuré SSL/HTTPS con Let's Encrypt
- [ ] Configuré Nginx como reverse proxy
- [ ] Creé backup automático via cron
- [ ] Testeé que pueda generar un APK
- [ ] Testeé que el APK se conecta al servidor
- [ ] Testeé que puedo controlar el host remotamente
- [ ] Configuré firewall para puertos 80, 443
- [ ] Cambié contraseña de PostgreSQL a algo fuerte
- [ ] Guardé SERVICE_KEY en lugar seguro

---

## Soporte

Para issues:
1. Revisa logs: `docker-compose logs -f`
2. Verifica estado: `docker-compose ps`
3. Reinicia si es necesario: `docker-compose down && docker-compose up -d`

---

**¡Tu servidor privado está listo para producción! 🎉**
