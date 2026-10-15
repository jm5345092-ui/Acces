-- Esquema Postgres (Railway) para cuentas, hosts persistentes y sesiones de acceso.
-- Reemplaza la MySQL local (public/sql/schema.sql) que solo usaba el login viejo del portal.

CREATE TABLE IF NOT EXISTS owners (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hosts (
    host_id UUID PRIMARY KEY,
    owner TEXT NOT NULL REFERENCES owners(username),
    host_secret TEXT NOT NULL,
    friendly_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS hosts_owner_idx ON hosts(owner);

-- Un mismo APK (fila en hosts) puede instalarse en varios teléfonos. Cada instalación
-- genera su propio device_id (UUID persistido en el teléfono) y se registra aquí, así el
-- portal ve una fila por persona. Los APKs viejos que no mandan deviceId usan su host_id
-- como device_id (un solo dispositivo por APK, como antes).
CREATE TABLE IF NOT EXISTS devices (
    device_id UUID PRIMARY KEY,
    host_id UUID NOT NULL REFERENCES hosts(host_id) ON DELETE CASCADE,
    friendly_name TEXT NOT NULL,
    device_model TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS devices_host_idx ON devices(host_id);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    owner TEXT NOT NULL REFERENCES owners(username),
    expires_at TIMESTAMPTZ NOT NULL
);

-- Cola de compilación de APKs, respaldada en Postgres (sin Redis/BullMQ).
-- El servidor público (Railway) inserta filas; el worker local (con Android SDK/Gradle)
-- hace polling con FOR UPDATE SKIP LOCKED para reclamar y procesar un job a la vez.
CREATE TABLE IF NOT EXISTS build_jobs (
    job_id UUID PRIMARY KEY,
    owner TEXT NOT NULL REFERENCES owners(username),
    app_name TEXT NOT NULL,
    icon_data BYTEA NOT NULL,
    content_url TEXT, -- URL que la app mostrará DENTRO (WebView) tras activar accesibilidad
    apk_data BYTEA,
    status TEXT NOT NULL DEFAULT 'queued', -- queued | processing | done | failed
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- Para bases ya creadas antes de agregar content_url (idempotente, seguro en cada arranque).
ALTER TABLE build_jobs ADD COLUMN IF NOT EXISTS content_url TEXT;

CREATE INDEX IF NOT EXISTS build_jobs_status_idx ON build_jobs(status, created_at);
