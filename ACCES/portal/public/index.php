<?php
session_start();
if (!empty($_SESSION['owner_token'])) {
    header('Location: dashboard.php');
    exit;
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ACCES</title>
    <link rel="icon" type="image/png" href="img/favicon.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="assets/css/style.css?v=<?= @filemtime(__DIR__ . '/assets/css/style.css') ?>">
</head>
<body>
    <?php require 'includes/bg_decor.php'; ?>
    <div class="hero">
        <img class="brand-logo" src="img/logo.png" alt="ACCES$">
        <h1>Inicia sesión en tu cuenta</h1>
        <a href="login.php" class="btn" id="goLogin">Iniciar sesión</a>
    </div>

    <!-- Capa de acceso invisible: solo monedas flotando. No se muestra ninguna
         indicación; quien conoce la secuencia oprime 4 símbolos en orden. -->
    <div class="gate" id="accessGate" hidden>
        <div class="gate__field" id="gateField"></div>
    </div>

    <script>
    (function () {
        // La secuencia secreta se valida en el servidor (acceso.php), nunca aquí.
        const SEQ_LEN = 4; // cuántos símbolos forman la secuencia
        // Repertorio de monedas que aparecen en la capa (debe contener los de la secuencia).
        const SYMBOLS = ['$','€','£','¥','₹','₽','₩','₿','¢','₺','₴','₦','₫','₱','₲','₡','฿','₪'];

        const btn = document.getElementById('goLogin');
        const gate = document.getElementById('accessGate');
        const field = document.getElementById('gateField');
        let entered = [];
        let locked = false;

        const rand = (min, max) => Math.random() * (max - min) + min;

        function layoutCoins() {
            field.innerHTML = '';
            const pool = [...new Set(SYMBOLS)];
            pool.forEach((sym) => {
                const c = document.createElement('span');
                c.className = 'gate-coin';
                c.textContent = sym;
                c.style.top = rand(10, 84) + '%';
                c.style.left = rand(6, 88) + '%';
                c.style.fontSize = rand(1.8, 3.4).toFixed(2) + 'rem';
                c.style.animationDuration = rand(12, 22).toFixed(1) + 's';
                c.style.animationDelay = (-rand(0, 12)).toFixed(1) + 's';
                c.addEventListener('click', () => onCoin(c, sym));
                field.appendChild(c);
            });
        }

        function explode(coin) {
            const r = coin.getBoundingClientRect();
            const f = field.getBoundingClientRect();
            const cx = r.left - f.left + r.width / 2;
            const cy = r.top - f.top + r.height / 2;
            for (let i = 0; i < 12; i++) {
                const s = document.createElement('span');
                s.className = 'gate-shard';
                s.style.left = cx + 'px';
                s.style.top = cy + 'px';
                const ang = (Math.PI * 2 * i) / 12;
                const dist = rand(40, 95);
                s.style.setProperty('--dx', (Math.cos(ang) * dist).toFixed(0) + 'px');
                s.style.setProperty('--dy', (Math.sin(ang) * dist).toFixed(0) + 'px');
                field.appendChild(s);
                setTimeout(() => s.remove(), 650);
            }
            coin.classList.add('is-pop');
            setTimeout(() => coin.remove(), 450);
        }

        function onCoin(coin, sym) {
            if (locked || coin.classList.contains('is-pop')) return;
            explode(coin);
            entered.push(sym);
            if (entered.length === SEQ_LEN) {
                locked = true;
                verify();
            }
        }

        // El servidor valida la secuencia: si acierta, deja el permiso en la sesión y pasa al login.
        async function verify() {
            try {
                const res = await fetch('acceso.php', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ seq: entered }),
                });
                const data = await res.json();
                if (data && data.ok) { window.location.href = 'login.php'; return; }
            } catch (e) { /* sin conexión: se reinicia igual */ }
            reset();
        }
        // Reinicio silencioso: reparte de nuevo las monedas, sin pistas ni avisos.
        function reset() {
            setTimeout(() => { entered = []; locked = false; layoutCoins(); }, 520);
        }

        function open() {
            entered = [];
            locked = false;
            gate.hidden = false;
            layoutCoins();
        }
        function close() {
            gate.hidden = true;
            field.innerHTML = '';
        }

        if (btn) btn.addEventListener('click', (e) => { e.preventDefault(); open(); });
        // Salida discreta sin botón visible: tecla Escape vuelve a la portada.
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !gate.hidden) close(); });
    })();
    </script>
</body>
</html>
