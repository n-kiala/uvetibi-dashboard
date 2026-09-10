#!/bin/bash

# Arrêter le script dès qu'une erreur survient
set -e

echo "=== [1/5] Mise à jour du système et installation des dépendances système (OpenCV & NumPy/Pandas natifs) ==="
sudo apt-get update
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-numpy \
    python3-pandas \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    ffmpeg

echo "=== [2/5] Création et activation de l'environnement virtuel avec partage des paquets système ==="
if [ ! -d "venv" ]; then
    python3 -m venv --system-site-packages venv
    echo "Environnement virtuel 'venv' créé avec succès."
else
    echo "L'environnement virtuel 'venv' existe déjà."
fi

# Activation de l'environnement
source venv/bin/activate

echo "=== [3/5] Mise à jour de pip dans l'environnement virtuel ==="
pip install --upgrade pip

echo "=== [4/5] Installation des bibliothèques spécifiques (Streamlit, PyArrow, Ultralytics, Google Cloud, bcrypt) ==="
pip install \
    streamlit \
    pyarrow \
    ultralytics \
    opencv-python-headless \
    bcrypt \
    google-cloud-bigquery \
    google-cloud-storage

echo "=== [5/5] Configuration du mode de compatibilité Streamlit pour ARM ==="
mkdir -p .streamlit
cat << 'EOF' > .streamlit/config.toml
[global]
dataFrameSerialization = "legacy"
EOF

echo "========================================================"
echo " Installation terminée avec succès !"
echo " Pour activer l'environnement, tapez : source venv/bin/activate"
echo " Pour lancer votre application : ./lancement_systemes.sh"
echo "========================================================"