<?php $currentPage = basename($_SERVER['PHP_SELF']); ?>
<nav class="top-menu">
    <span class="top-menu__brand"><img src="img/logo.png" alt="ACCES$">ACCES$</span>
    <div class="top-menu__links">
        <a href="dashboard.php" class="<?= $currentPage === 'dashboard.php' ? 'active' : '' ?>">Dashboard</a>
        <a href="conectar.php" class="<?= $currentPage === 'conectar.php' ? 'active' : '' ?>">Conectar</a>
        <a href="ver.php" class="<?= $currentPage === 'ver.php' ? 'active' : '' ?>">Ver</a>
        <a href="/webserver/" target="_blank" rel="noopener">APK Decompiler</a>
        <a href="logout.php" class="top-menu__salir">Salir</a>
    </div>
</nav>
