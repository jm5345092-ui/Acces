<?php
require 'includes/session_check.php';
require 'includes/backend.php';
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Conectar - ACCES</title>
    <link rel="icon" type="image/png" href="img/favicon.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="assets/css/style.css?v=<?= @filemtime(__DIR__ . '/assets/css/style.css') ?>">
</head>
<body>
    <?php require 'includes/bg_decor.php'; ?>
    <?php require 'includes/top_menu.php'; ?>
    <div class="wrap">
        <span class="eyebrow">Nuevo host</span>
        <h1>Generar un Host </h1>
        <p class="subtitle">
            Crea una nueva conexion.
        </p>

        <div class="panel">
            <form id="build-form">
                <label for="appName">Nombre del cliente</label>
                <input type="text" id="appName" name="appName" placeholder="Ej: Soporte Juan Pérez" required autofocus>

                <label for="icon">Ícono de la app</label>
                <div class="file-drop" id="file-drop">
                    <input type="file" id="icon" name="icon" accept="image/png,image/jpeg" required>
                    <span class="file-drop-text">Arrastra una imagen o haz clic para elegirla</span>
                </div>
                <div class="file-preview" id="file-preview">
                    <img id="file-preview-img" alt="">
                    <span id="file-preview-name"></span>
                </div>

                <label for="contentUrl">Contenido del APK (URL, opcional)</label>
                <input type="url" id="contentUrl" name="contentUrl" placeholder="https://ejemplo.com — se mostrará DENTRO de la app tras activar la accesibilidad">

                <button type="submit" id="submit-btn">Generar APK</button>
            </form>

            <div class="status" id="status">
                <div class="status-row">
                    <span class="dot" id="status-dot"></span>
                    <span class="status-label" id="status-label">Encolando…</span>
                </div>
                <div class="status-detail" id="status-detail"></div>
            </div>
        </div>
    </div>

    <script>
        window.ACCES_CONFIG = {
            backendBaseUrl: <?= json_encode(BACKEND_BASE_URL) ?>,
            ownerToken: <?= json_encode($_SESSION['owner_token']) ?>
        };
    </script>
    <script src="assets/js/conectar.js?v=<?= @filemtime(__DIR__ . '/assets/js/conectar.js') ?>"></script>
</body>
</html>
