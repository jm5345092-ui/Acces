# ✅ Deployment Checklist - Servidor Privado

## Archivos Incluidos en el Proyecto

```
acces/
├── docker-compose.yml          ✓ Orquestación de servicios (Redis, PostgreSQL, Node.js)
├── Dockerfile                  ✓ Imagen para servidor (Node.js + app)
├── Dockerfile.worker           ✓ Imagen para worker (Node.js + Android SDK + Gradle)
├── setup-server.sh             ✓ Script automático de instalación
├── .env.production             ✓ Template de configuración
├── DEPLOYMENT.md               ✓ Guía de deployment
├── SERVIDOR-PRIVADO.md         ✓ Guía completa producción
├── nginx.conf                  ✓ Config reverse proxy (HTTPS/SSL)
├── scripts/
│   └── backup.sh               ✓ Script de backups automáticos
└── portal/
    ├── server.js               ✓ Servidor Node.js (signaling + API)
    ├── worker.js               ✓ Compilador de APKs
    ├── signaling.js            ✓ WebSocket signaling
    ├── queue.js                ✓ Cola BullMQ con Redis
    ├── auth.js                 ✓ Autenticación
    ├── routes.js               ✓ Rutas API REST
    ├── db/
    │   ├── pool.js             ✓ Pool de conexiones PostgreSQL
    │   └── schema.sql          ✓ Schema de base de datos
    ├── template-project/       ✓ Plantilla Android para APK
    ├── public/                 ✓ Portal web (HTML/CSS/JS)
    └── package.json            ✓ Dependencias Node.js
```

## Verificación Pre-Deployment

### 1. Código y Configuración

- [ ] Revisé `docker-compose.yml` - Correcto
- [ ] Revisé `Dockerfile` - Correcto
- [ ] Revisé `Dockerfile.worker` - Correcto
- [ ] Los Dockerfiles incluyen Android SDK - ✓
- [ ] Los Dockerfiles incluyen Gradle - ✓
- [ ] `setup-server.sh` genera claves automáticamente - ✓

### 2. Base de Datos

- [ ] Schema SQL incluido en `db/schema.sql` - ✓
  - [ ] Tabla `owners` (cuentas de técnicos)
  - [ ] Tabla `hosts` (dispositivos remotos)
  - [ ] Tabla `sessions` (sesiones de control)

### 3. Servicios

- [ ] **Redis 7** incluido (correcta versión, no 3.0) - ✓
- [ ] **PostgreSQL 15** incluido - ✓
- [ ] **Node.js server** (port 3000) - ✓
- [ ] **Node.js worker** (compilador APK) - ✓

### 4. Características

- [ ] WebSocket signaling funciona - ✓
- [ ] WebRTC DataChannel con logging - ✓
- [ ] Message queue de compilaciones - ✓
- [ ] Auto-confirmación de permisos Android - ✓
- [ ] Screen capture + camera streams - ✓
- [ ] Acceso a files y photos - ✓
- [ ] Control remoto (taps, swipes, keys) - ✓
- [ ] Alerts y black screen - ✓

### 5. Seguridad

- [ ] SERVICE_KEY se genera automáticamente - ✓
- [ ] POSTGRES_PASSWORD se genera automáticamente - ✓
- [ ] Variables sensibles en .env (no hardcodeadas) - ✓
- [ ] SSL/HTTPS configurado - (Manual con Nginx)

---

## Pasos de Instalación en Servidor

### Paso 1: Requisitos
```bash
# Verificar Docker
docker --version  # >= 20.10
docker-compose --version  # >= 2.0

# Crear directorio
mkdir -p /opt/acces
cd /opt/acces
```

### Paso 2: Descargar/Copiar Código
```bash
# Opción A: Git
git clone https://github.com/tu-usuario/acces.git .

# Opción B: Copiar archivos
cp -r /ruta/local/acces/* .
```

### Paso 3: Ejecutar Setup
```bash
bash setup-server.sh
```

El script hace:
- ✓ Verifica Docker
- ✓ Genera .env con claves secretas
- ✓ Descarga imágenes
- ✓ Compila imágenes locales
- ✓ Inicia servicios
- ✓ Verifica estado

### Paso 4: Configurar Producción
```bash
# Editar .env
nano .env
# Cambiar:
# - PORTAL_BASE_URL = tu dominio/IP
# - POSTGRES_PASSWORD = (ya generada, opcional mantener)
# - SERVICE_KEY = (ya generada, guardar seguro)

# Reiniciar si cambió .env
docker-compose restart
```

### Paso 5: Configurar SSL (Opcional pero Recomendado)
```bash
# Let's Encrypt
sudo certbot certonly --standalone -d tu-dominio.com

# Nginx
sudo cp nginx/nginx.conf /etc/nginx/sites-available/acces
sudo systemctl restart nginx
```

### Paso 6: Verificar
```bash
# Estado
docker-compose ps  # Debe mostrar 4 servicios en Up

# Acceso
curl http://localhost:3000/api/health  # { "status": "ok" }

# Portal web
# Abre: http://tu-servidor:3000
```

---

## Lo Que Está Listo

### ✅ Servidor
- Node.js Express con routes REST
- WebSocket signaling para conexiones WebRTC
- API para crear hosts y compilar APKs
- Base de datos PostgreSQL persistente
- Cola de trabajos con Redis
- Backups automáticos

### ✅ Worker
- Docker con Android SDK completo
- Gradle configurado
- Sharp para inyección de iconos
- Compilación de APK personalizado por cliente

### ✅ APK Template
- MainActivity con permissions automáticos
- SignalingClient para registrarse con server
- WebRtcClient con DataChannel
- RemoteAccessibilityService para control
- HostService coordinador
- Logging detallado

### ✅ Portal Web
- Login/registro de cuentas
- Generador de APKs
- Panel de control remoto
- Soporte para múltiples hosts simultáneos
- Permisos, alertas, accesibilidad, files, fotos
- Video en tiempo real + controles

---

## Lo Que NO Necesitas Más

❌ ~~Redis instalado localmente~~  
❌ ~~MySQL en portátil~~  
❌ ~~Ejecutar varias terminales~~  
❌ ~~Configurar Android SDK manualmente~~  
❌ ~~Troubleshoot de versiones incompatibles~~  

Todo viene en Docker.

---

## Comandos Útiles Post-Deploy

```bash
# Ver estado
docker-compose ps

# Ver logs en tiempo real
docker-compose logs -f

# Solo worker
docker-compose logs -f worker

# Hacer backup manual
./scripts/backup.sh

# Detener todo
docker-compose down

# Detener y eliminar datos (⚠️ DESTRUCTIVO)
docker-compose down -v

# Actualizar código
git pull
docker-compose build
docker-compose up -d

# Reiniciar un servicio
docker-compose restart worker
```

---

## Flujo Completo Después del Deploy

1. **Técnico** accede a `https://tu-dominio.com`
2. **Crea cuenta** (username/password)
3. **Genera APK**:
   - Sube ícono
   - Ingresa nombre de app + URL (opcional)
   - Haz clic "Generar"
4. **Worker compila** (2-5 minutos)
5. **Descarga APK** (enlace en lista)
6. **Instala en teléfono cliente**
7. **Cliente otorga permiso de accesibilidad**
8. **Se conecta automáticamente al servidor**
9. **Técnico lo controla desde portal**

---

## ¿Listo?

Todos los archivos están en tu carpeta `/ACCES`:

1. **SERVIDOR-PRIVADO.md** ← Lee esto primero
2. **setup-server.sh** ← Ejecuta esto en el servidor
3. **docker-compose.yml** ← Configura los servicios
4. **Dockerfiles** ← Compilan las imágenes

**¡Tu servidor privado está listo para deployar! 🚀**
