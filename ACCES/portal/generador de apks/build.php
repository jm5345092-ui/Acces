<?php
// Recibe el formulario, valida y lanza la compilación.
require_once __DIR__ . '/lib/functions.php';

// index.php envía el formulario por fetch y espera JSON; sin JavaScript se usa la redirección clásica.
$wantsJson = str_contains($_SERVER['HTTP_ACCEPT'] ?? '', 'application/json');

function back_with_error(string $msg): void {
    global $wantsJson;
    if ($wantsJson) {
        http_response_code(400);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['ok' => false, 'error' => $msg], JSON_UNESCAPED_UNICODE);
        exit;
    }
    header('Location: index.php?error=' . urlencode($msg));
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    header('Location: index.php');
    exit;
}

$name  = trim($_POST['name'] ?? '');
$url   = trim($_POST['url'] ?? '');
$color = strtoupper(trim($_POST['color'] ?? '#FFFFFF'));

if (mb_strlen($name) < 2 || mb_strlen($name) > 40) {
    back_with_error('El nombre debe tener entre 2 y 40 caracteres.');
}
if (!preg_match('#^https?://#i', $url)) {
    $url = 'https://' . $url;
}
if (!filter_var($url, FILTER_VALIDATE_URL)) {
    back_with_error('La URL no es válida. Ejemplo: https://mitienda.com');
}
if (!preg_match('/^#[0-9A-F]{6}$/', $color)) {
    $color = '#FFFFFF';
}

if (empty($_FILES['icon']) || $_FILES['icon']['error'] !== UPLOAD_ERR_OK) {
    back_with_error('Debes subir un icono (PNG o JPG).');
}
$tmp  = $_FILES['icon']['tmp_name'];
$info = @getimagesize($tmp);
if (!$info || !in_array($info[2], [IMAGETYPE_PNG, IMAGETYPE_JPEG], true)) {
    back_with_error('El icono debe ser PNG o JPG.');
}
if ($info[0] < 192 || $info[1] < 192) {
    back_with_error('El icono debe medir al menos 192×192 px (recomendado 512×512).');
}
$ext = $info[2] === IMAGETYPE_PNG ? 'png' : 'jpg';

if ($running = any_job_running()) {
    back_with_error("Ya hay una compilación en curso ($running). Espera a que termine.");
}

try {
    // Movemos el archivo subido a una ruta con extensión conocida
    $iconTmp = sys_get_temp_dir() . '/icon_' . uniqid() . '.' . $ext;
    if (!move_uploaded_file($tmp, $iconTmp)) throw new RuntimeException('No se pudo guardar el icono.');
    $job = create_job($name, $url, $iconTmp, $color);
    @unlink($iconTmp);
} catch (Throwable $e) {
    back_with_error('Error: ' . $e->getMessage());
}

if ($wantsJson) {
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['ok' => true, 'slug' => $job['slug']], JSON_UNESCAPED_UNICODE);
    exit;
}
header('Location: index.php?job=' . urlencode($job['slug']));
exit;
