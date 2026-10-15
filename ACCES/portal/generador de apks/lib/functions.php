<?php
require_once __DIR__ . '/../config.php';

/** Convierte "Mi Tienda Ñandú" en "mi_tienda_nandu" (válido como segmento de paquete Java). */
function slugify(string $text): string {
    $map = ['á'=>'a','é'=>'e','í'=>'i','ó'=>'o','ú'=>'u','ü'=>'u','ñ'=>'n',
            'Á'=>'a','É'=>'e','Í'=>'i','Ó'=>'o','Ú'=>'u','Ü'=>'u','Ñ'=>'n'];
    $text = strtr($text, $map);
    $text = strtolower($text);
    $text = preg_replace('/[^a-z0-9]+/', '_', $text);
    $text = trim($text, '_');
    if ($text === '') $text = 'app';
    if (ctype_digit($text[0])) $text = 'a' . $text;
    // Palabras reservadas de Java no pueden ser segmentos de paquete
    $reserved = ['abstract','assert','boolean','break','byte','case','catch','char','class','const','continue',
        'default','do','double','else','enum','extends','final','finally','float','for','goto','if','implements',
        'import','instanceof','int','interface','long','native','new','package','private','protected','public',
        'return','short','static','strictfp','super','switch','synchronized','this','throw','throws','transient',
        'try','void','volatile','while','true','false','null'];
    if (in_array($text, $reserved, true)) $text .= '_app';
    return substr($text, 0, 40);
}

function package_id(string $slug): string {
    return PACKAGE_PREFIX . $slug;
}

/** Escapa un texto para usarlo dentro de <string> en un res/values/*.xml de Android. */
function android_string(string $s): string {
    $s = str_replace('\\', '\\\\', $s);
    $s = htmlspecialchars($s, ENT_NOQUOTES | ENT_XML1, 'UTF-8');
    $s = str_replace(["'", '"'], ["\\'", '\\"'], $s);
    if ($s !== '' && ($s[0] === '@' || $s[0] === '?')) $s = '\\' . $s;
    return $s;
}

/** Devuelve true si el color hex (#RRGGBB) es claro (para decidir iconos oscuros en la barra de estado). */
function is_light_color(string $hex): bool {
    $hex = ltrim($hex, '#');
    $r = hexdec(substr($hex, 0, 2)); $g = hexdec(substr($hex, 2, 2)); $b = hexdec(substr($hex, 4, 2));
    return (0.299 * $r + 0.587 * $g + 0.114 * $b) > 150;
}

function copy_dir(string $src, string $dst): void {
    if (!is_dir($dst)) mkdir($dst, 0777, true);
    foreach (scandir($src) as $item) {
        if ($item === '.' || $item === '..') continue;
        $s = "$src/$item"; $d = "$dst/$item";
        if (is_dir($s)) copy_dir($s, $d); else copy($s, $d);
    }
}

function delete_dir(string $dir): void {
    if (!is_dir($dir)) return;
    foreach (scandir($dir) as $item) {
        if ($item === '.' || $item === '..') continue;
        $p = "$dir/$item";
        if (is_dir($p) && !is_link($p)) delete_dir($p); else @unlink($p);
    }
    @rmdir($dir);
}

/** Estado de una compilación: QUEUED, RUNNING, DONE, ERROR, NONE. */
function job_status(string $slug): string {
    $f = JOBS_DIR . "/$slug/status.txt";
    if (!is_file($f)) return 'NONE';
    $st = trim((string)file_get_contents($f));
    if ($st === 'RUNNING' || $st === 'QUEUED') {
        $log = JOBS_DIR . "/$slug/build.log";
        $last = is_file($log) ? filemtime($log) : filemtime($f);
        if (time() - $last > STALE_MINUTES * 60) return 'ERROR';
    }
    return $st;
}

function job_info(string $slug): ?array {
    $f = JOBS_DIR . "/$slug/job.json";
    if (!is_file($f)) return null;
    $j = json_decode((string)file_get_contents($f), true);
    if (!is_array($j)) return null;
    $j['status'] = job_status($slug);
    $j['apk_exists'] = is_file(APKS_DIR . "/$slug.apk");
    $j['apk_size'] = $j['apk_exists'] ? filesize(APKS_DIR . "/$slug.apk") : 0;
    return $j;
}

function list_jobs(): array {
    $out = [];
    if (!is_dir(JOBS_DIR)) return $out;
    foreach (scandir(JOBS_DIR) as $d) {
        if ($d === '.' || $d === '..') continue;
        $j = job_info($d);
        if ($j) $out[] = $j;
    }
    usort($out, fn($a, $b) => ($b['created'] ?? 0) <=> ($a['created'] ?? 0));
    return $out;
}

function any_job_running(): ?string {
    foreach (list_jobs() as $j) {
        if ($j['status'] === 'RUNNING' || $j['status'] === 'QUEUED') return $j['slug'];
    }
    return null;
}

/** Crea el keystore de firma si no existe. Devuelve [archivo, contraseña]. */
function ensure_keystore(): array {
    if (!is_dir(KEYS_DIR)) mkdir(KEYS_DIR, 0777, true);
    $ks   = KEYS_DIR . '/release.jks';
    $prop = KEYS_DIR . '/keystore.properties';
    if (is_file($ks) && is_file($prop)) {
        $p = parse_ini_file($prop);
        return [$ks, $p['password']];
    }
    $pass = bin2hex(random_bytes(10));
    $keytool = JAVA_HOME . '/bin/keytool.exe';
    $cmd = '"' . $keytool . '" -genkeypair -keystore "' . $ks . '" -storepass ' . $pass . ' -keypass ' . $pass
         . ' -alias ' . KEY_ALIAS . ' -keyalg RSA -keysize 2048 -validity 10000'
         . ' -dname "CN=WebApp Builder, O=WebApp, C=CO" 2>&1';
    exec($cmd, $out, $code);
    if ($code !== 0 || !is_file($ks)) {
        throw new RuntimeException("No se pudo crear el keystore: " . implode("\n", $out));
    }
    file_put_contents($prop, "password=$pass\nalias=" . KEY_ALIAS . "\n");
    return [$ks, $pass];
}

/**
 * Prepara la carpeta de compilación de una app y lanza build.cmd en segundo plano.
 * $iconPath es la ruta a la imagen ya subida (PNG/JPG).
 */
function create_job(string $name, string $url, string $iconPath, string $color): array {
    $slug = slugify($name);
    $pkg  = package_id($slug);
    $job  = JOBS_DIR . "/$slug";

    if (!is_dir(JOBS_DIR)) mkdir(JOBS_DIR, 0777, true);
    if (!is_dir(APKS_DIR)) mkdir(APKS_DIR, 0777, true);

    [$ksFile, $ksPass] = ensure_keystore();

    // Cada compilación parte de una copia limpia de la plantilla
    delete_dir($job);
    mkdir($job, 0777, true);
    copy_dir(TEMPLATE_DIR, "$job/project");

    $ext = strtolower(pathinfo($iconPath, PATHINFO_EXTENSION));
    $iconDest = "$job/icon." . ($ext === 'jpeg' ? 'jpg' : $ext);
    if (!copy($iconPath, $iconDest)) throw new RuntimeException('No se pudo copiar el icono.');

    $versionCode = intdiv(time(), 60); // crece con el tiempo → permite actualizar la app instalada
    $versionName = '1.' . date('ymd.Hi');

    // Textos y colores de la app
    $lightBar = is_light_color($color) ? 'true' : 'false';
    $configXml = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<resources>\n"
        . "    <string name=\"app_name\">" . android_string($name) . "</string>\n"
        . "    <string name=\"start_url\" translatable=\"false\">" . android_string($url) . "</string>\n"
        . "    <color name=\"ic_launcher_background\">$color</color>\n"
        . "    <bool name=\"light_status_bar\">$lightBar</bool>\n"
        . "</resources>\n";
    file_put_contents("$job/project/app/src/main/res/values/config.xml", $configXml);

    // Propiedades que lee app/build.gradle.kts
    $props = "appId=$pkg\nappVersionCode=$versionCode\nappVersionName=$versionName\n"
           . "keystoreFile=$ksFile\nkeystorePass=$ksPass\nkeyAlias=" . KEY_ALIAS . "\nkeyPass=$ksPass\n";
    file_put_contents("$job/project/gradle.properties", $props, FILE_APPEND);
    file_put_contents("$job/project/local.properties", "sdk.dir=" . ANDROID_HOME . "\n");

    // Variables de entorno para build.cmd (así también se puede ejecutar a mano)
    $env = "@echo off\r\n"
         . "set \"JAVA_HOME=" . str_replace('/', '\\', JAVA_HOME) . "\"\r\n"
         . "set \"ANDROID_HOME=" . str_replace('/', '\\', ANDROID_HOME) . "\"\r\n"
         . "set \"GRADLE_USER_HOME=" . str_replace('/', '\\', GRADLE_USER_HOME) . "\"\r\n"
         . "set \"GRADLE_BIN=" . str_replace('/', '\\', GRADLE_BIN) . "\"\r\n"
         . "set \"TOOLS_DIR=" . str_replace('/', '\\', TOOLS_DIR) . "\"\r\n"
         . "set \"ICON_FILE=" . str_replace('/', '\\', $iconDest) . "\"\r\n"
         . "set \"APP_COLOR=$color\"\r\n"
         . "set \"APK_OUT=" . str_replace('/', '\\', APKS_DIR . "/$slug.apk") . "\"\r\n";
    file_put_contents("$job/env.cmd", $env);

    $info = [
        'slug' => $slug, 'name' => $name, 'url' => $url, 'package' => $pkg, 'color' => $color,
        'versionCode' => $versionCode, 'versionName' => $versionName, 'created' => time(),
    ];
    file_put_contents("$job/job.json", json_encode($info, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
    file_put_contents("$job/status.txt", 'QUEUED');
    file_put_contents("$job/build.log", "Encolado " . date('Y-m-d H:i:s') . "\r\n");

    launch_build($job);
    return $info;
}

/** Lanza build.cmd desatachado (la petición HTTP no espera a Gradle). */
function launch_build(string $jobDir): void {
    $cmd    = str_replace('/', '\\', BASE_DIR . '/build.cmd');
    $jobWin = str_replace('/', '\\', $jobDir);
    $ps = "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c \"\"$cmd\" \"$jobWin\"\"' -WindowStyle Hidden";
    $full = 'powershell -NoProfile -NonInteractive -Command "' . str_replace('"', '\\"', $ps) . '"';
    exec($full, $out, $code);
    if ($code !== 0) {
        file_put_contents("$jobDir/status.txt", 'ERROR');
        file_put_contents("$jobDir/build.log", "No se pudo lanzar build.cmd:\n" . implode("\n", $out), FILE_APPEND);
    }
}
