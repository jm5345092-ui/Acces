<?php
// Configuración de rutas del generador de apps.
// Ajusta estas rutas si cambias de máquina.

define('BASE_DIR',     str_replace('\\', '/', __DIR__));
define('TEMPLATE_DIR', BASE_DIR . '/template');
define('JOBS_DIR',     BASE_DIR . '/jobs');
define('APKS_DIR',     BASE_DIR . '/apks');
define('KEYS_DIR',     BASE_DIR . '/keys');
define('TOOLS_DIR',    BASE_DIR . '/tools');

// JDK que trae Android Studio (Java 25)
define('JAVA_HOME',   'C:/Program Files/Android/Android Studio/jbr');
// SDK de Android
define('ANDROID_HOME', 'C:/Users/hueso/AppData/Local/Android/Sdk');
// Gradle 9.7.1 (ya descargado por Android Studio)
define('GRADLE_BIN',  'C:/Users/hueso/.gradle/wrapper/dists/gradle-9.7.1-bin/1w1c7tv4s851m17nbqdsro2tv/gradle-9.7.1/bin/gradle.bat');
// Caché de Gradle (para reutilizar dependencias ya descargadas)
define('GRADLE_USER_HOME', 'C:/Users/hueso/.gradle');

// Prefijo del identificador de paquete: com.webapp.<slug>
define('PACKAGE_PREFIX', 'com.webapp.');

// Alias de la llave de firma
define('KEY_ALIAS', 'webapp');

// Minutos sin actividad en el log para considerar una compilación colgada
define('STALE_MINUTES', 30);
