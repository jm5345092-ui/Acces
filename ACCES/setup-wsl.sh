#!/bin/bash
# Script de setup para WSL - Instala PostgreSQL
# (la cola de compilación de APKs usa Postgres directamente, no requiere Redis)

echo "================================"
echo "Setup ACCES en WSL"
echo "================================"

echo ""
echo "Instalando PostgreSQL..."
sudo apt update
sudo apt install postgresql postgresql-contrib -y

echo ""
echo "Iniciando PostgreSQL..."
sudo service postgresql start

echo ""
echo "Creando usuario y base de datos..."
sudo -u postgres psql -c "CREATE USER acces WITH PASSWORD 'acces';"
sudo -u postgres psql -c "CREATE DATABASE acces OWNER acces;"
sudo -u postgres psql -c "ALTER USER acces CREATEDB;"

echo ""
echo "Verificando PostgreSQL..."
sudo -u postgres psql -c "SELECT 1" acces

echo ""
echo "================================"
echo "PostgreSQL está listo"
echo "================================"
echo ""
echo "Ahora en PowerShell, ejecuta:"
echo "cd C:\xampp\htdocs\ACCES\portal"
echo "npm start"
echo ""
