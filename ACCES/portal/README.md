# Portal generador de APKs de control remoto

## Requisitos previos

1. **Node.js** 18+
2. **Redis** corriendo localmente (o remoto)
   - Instalar: `sudo apt install redis-server` (Linux) o `brew install redis` (Mac)
   - Iniciar: `redis-server`
3. **Android SDK Command-Line Tools** + **Gradle** (necesarios para que el worker compile los APKs)
4. Un **keystore** para firmar los APKs generados:
   ```bash
   keytool -genkey -v -keystore mi-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias miapp
   ```

## Instalación

```bash
npm install
cp .env.example .env
# edita .env con tus rutas reales de keystore
```

## Ejecutar en desarrollo

Necesitas 2 terminales abiertas:

```bash
# Terminal 1 — API del portal
npm run start

# Terminal 2 — Worker que procesa los builds
npm run worker
```

## Probar el endpoint

```bash
curl -X POST http://localhost:3000/api/apps \
  -F "appName=Soporte Cliente X" \
  -F "signalingUrl=https://tuservidor.com/session/abc123" \
  -F "icon=@/ruta/a/tu/icono.png"
```

Respuesta:
```json
{ "jobId": "xxxx-xxxx", "status": "queued", "queueJobId": "1" }
```

Consultar estado:
```bash
curl http://localhost:3000/api/apps/xxxx-xxxx
```

## Pendiente

- [ ] `template-project/` — el proyecto Android base (aún no incluido, se arma en la siguiente fase)
- [ ] Dockerfile para aislar el entorno de build (Android SDK + Gradle)
- [ ] Frontend del formulario (link, ícono, nombre)
