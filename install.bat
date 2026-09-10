@echo off
setlocal enabledelayedexpansion

echo === [1/4] Verification de l'environnement Python pour Windows ===
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Erreur : Python n'est pas installe ou n'est pas dans le PATH de Windows.
    echo Veuillez installer Python depuis https://www.python.org/ en cochant "Add Python to PATH".
    pause
    exit /b %errorlevel%
)

echo === [2/4] Creation et activation de l'environnement virtuel Python ===
if not exist "venv" (
    python -m venv venv
    echo Environnement virtuel 'venv' cree avec succes.
) else (
    echo L'environnement virtuel 'venv' existe deja.
)

:: Activation de l'environnement virtuel sous Windows
call venv\Scripts\activate

echo === [3/4] Mise a jour de pip dans l'environnement virtuel ===
python -m pip install --upgrade pip

echo === [4/4] Installation des bibliothèques Python necessaires pour le Dashboard TIBI ===
pip install ^
    streamlit ^
    pandas ^
    numpy ^
    opencv-python-headless ^
    ultralytics ^
    bcrypt ^
    google-cloud-bigquery ^
    google-cloud-storage ^
    plotly

echo ========================================================
echo  Installation terminee avec succes !
echo  Pour activer l'environnement, tapez : venv\Scripts\activate
echo  Pour lancer votre application : streamlit run app.py
echo ========================================================
pause