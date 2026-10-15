# Generador de Apps (web → APK Android)

Formulario web que convierte la página de un emprendimiento en una app Android:
se ingresa nombre, URL e icono, y se obtiene un `.apk` firmado que al abrirse
carga la página dentro de la app (WebView), sin abrir el navegador.

Abrir en el navegador: `http://localhost/pruebas/`

## Cómo funciona

1. `index.php` muestra el formulario y, mientras compila, el log en vivo.
2. `build.php` valida los datos y llama a `create_job()` (`lib/functions.php`), que:
   - copia `template/` (proyecto Android mínimo) a `jobs/<slug>/project/`,
   - escribe nombre/URL/color en `res/values/config.xml` y el `applicationId` en `gradle.properties`,
   - crea el keystore de firma en `keys/` la primera vez,
   - lanza `build.cmd` en segundo plano.
3. `build.cmd` genera los iconos (`tools/IconGen.java`), ejecuta Gradle y copia el APK a `apks/<slug>.apk`.
4. `status.php` devuelve el estado y el log; la página lo consulta cada 3 s y al terminar muestra el enlace y un QR.

Rutas del JDK, SDK y Gradle están en `config.php`.

## Requisitos (ya presentes en esta máquina)

- Android Studio (aporta el JDK en `jbr/`), SDK con `platforms/android-34` y `build-tools/36.0.0`.
- Gradle 9.7.1 y AGP 9.4.0 en la caché de `~/.gradle` (se descargan automáticamente si faltan; necesita internet).
- XAMPP con `AllowOverride All` (por defecto) para que funcionen los `.htaccess`.

La primera compilación tarda 1–3 minutos; las siguientes unos 10–20 segundos (daemon de Gradle).

## Instalación en el celular

- Escanear el QR o abrir el enlace del APK desde el celular (misma red Wi‑Fi que el PC, usando la IP del PC en vez de `localhost`).
- Android pedirá permitir "instalar apps de origen desconocido".
- Si se vuelve a generar la misma app (mismo nombre), el `versionCode` sube y se instala como actualización.

## Importante

- **No borrar la carpeta `keys/`.** Contiene la llave con la que se firman todas las apps. Si se pierde,
  las apps ya instaladas no podrán actualizarse (habría que desinstalarlas). Haz una copia de seguridad.
- **Google Play** suele rechazar apps que solo envuelven una web (política de "funcionalidad mínima").
  Este generador está pensado para distribuir el APK directamente (enlace, WhatsApp, QR).
- **iOS** no es posible con este método: requiere Mac, cuenta de desarrollador de Apple y la App Store
  rechaza apps que son solo un WebView. Para iPhone la alternativa es una PWA ("Añadir a pantalla de inicio").
- Se compila una app a la vez.

## Qué hace la app generada

- WebView a pantalla completa con la URL configurada, barra de progreso y splash con el color e icono elegidos.
- Enlaces `tel:`, `mailto:`, `whatsapp:`, `intent:` se abren en la app correspondiente; el resto queda dentro.
- Botón atrás navega el historial; `target="_blank"` se abre en la misma vista; subida de archivos desde formularios.
- Página "Sin conexión" con botón de reintento.
