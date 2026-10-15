<?php
session_start();
require 'includes/backend.php';

if (!empty($_SESSION['owner_token'])) {
    header('Location: dashboard.php');
    exit;
}

// La capa de acceso es obligatoria: sin el permiso que otorga acceso.php, no se
// puede llegar al login ni escribiendo la URL ni con el botón atrás.
if (empty($_SESSION['gate_passed'])) {
    header('Location: index.php');
    exit;
}

// Sin caché: evita que el botón atrás muestre una copia guardada del login
// saltándose la verificación de la capa.
header('Cache-Control: no-cache, no-store, must-revalidate');
header('Pragma: no-cache');
header('Expires: 0');

$error = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $usuario = trim($_POST['usuario'] ?? '');
    $password = $_POST['password'] ?? '';

    if ($usuario === '' || $password === '') {
        $error = 'Ingresa usuario y contraseña.';
    } else {
        $result = backend_request('POST', '/api/login', [
            'username' => $usuario,
            'password' => $password,
        ]);

        error_log("[Login] status=" . $result['status'] . ", body=" . json_encode($result['body']));

        if ($result['status'] === 200 && !empty($result['body']['ownerToken'])) {
            session_regenerate_id(true);
            $_SESSION['owner_token'] = $result['body']['ownerToken'];
            $_SESSION['usuario_nombre'] = $result['body']['username'];
            error_log("[Login] ✓ Token guardado: " . substr($_SESSION['owner_token'], 0, 16) . "...");
            header('Location: dashboard.php');
            exit;
        }

        error_log("[Login] ✗ Login falló");
        $error = 'Usuario o contraseña incorrectos.';
    }
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Iniciar sesión - ACCES</title>
    <link rel="icon" type="image/png" href="img/favicon.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="assets/css/style.css?v=<?= @filemtime(__DIR__ . '/assets/css/style.css') ?>">
</head>
<body>
    <?php require 'includes/bg_decor.php'; ?>
    <div class="hero">
        <div class="login-card">
            <img class="brand-logo" src="img/logo.png" alt="ACCES$">
            <h1>Iniciar sesión</h1>
            <?php if ($error): ?>
                <div class="error-msg"><?= htmlspecialchars($error) ?></div>
            <?php endif; ?>
            <form method="POST" action="login.php">
                <label for="usuario">Usuario</label>
                <input type="text" id="usuario" name="usuario" autocomplete="username" required autofocus>

                <label for="password">Contraseña</label>
                <input type="password" id="password" name="password" autocomplete="current-password" required>

                <button type="submit" class="btn">Entrar</button>
            </form>
        </div>
        <a href="index.php" class="back-link">&larr; Volver</a>
    </div>
</body>
</html>
